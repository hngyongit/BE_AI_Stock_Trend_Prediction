from __future__ import annotations

import concurrent.futures
import logging
import time
from datetime import datetime
from typing import Any, Dict, List
from bson.objectid import ObjectId

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.core.browser import VietstockBrowser
from vietstock_crawler.core.logging_config import configure_logging
from vietstock_crawler.models.columns import FINANCIAL_COLUMNS, MARKET_COLUMNS, TRADING_STATS_COLUMNS
from vietstock_crawler.parsers.trading_stats_parser import crawl_trading_stats
from vietstock_crawler.services.google_sheets_service import (
    append_records_with_titles,
    get_daily_run_index,
    get_gspread_client,
    read_config,
    should_run_trading_stats_today,
)
from vietstock_crawler.services.mongodb_service import MongoDBService
from vietstock_crawler.services.vietstock_service import crawl_company
from vietstock_crawler.utils.date_utils import (
    dated_sheet_name,
    latest_completed_quarter_suffix,
    output_sheet_name,
    parse_quarter_suffix,
    resolve_latest_reported_quarter_suffix,
)
from vietstock_crawler.utils.text_utils import clean_config_text
from vietstock_crawler.utils.url_utils import normalize_slug_value


def crawl_single_stock_daily(
    item: dict[str, Any],
    idx: int,
    symbols_count: int,
    settings: Any,
    db_service: MongoDBService,
    run_trading_stats: bool,
    data_source_id: ObjectId | None,
    log_id: ObjectId | None,
    timeout: float | None = None
) -> dict[str, Any]:
    """
    Crawls a single stock symbol for the daily job and records it.
    Uses its own VietstockBrowser session for thread-safety.
    """
    symbol = clean_config_text(item.get("symbol")).upper()
    slug = normalize_slug_value(item.get("slug"))

    if not symbol:
        return {"status": "SKIPPED", "message": "Symbol is empty"}

    stock_id = item.get("stock_id")
    market_id = item.get("market_id")
    industry_id = item.get("industry_id")
    
    # Retrieve or create stock data source details from DB if connected
    market_price_data_url = ""
    stock_data_source_id = item.get("data_source_id") or data_source_id
    
    if db_service.is_connected():
        # 1. Resolve stock_id, market_id, industry_id if missing
        if not stock_id:
            s_doc = db_service.db["dimstocks"].find_one({"symbol": symbol})
            if s_doc:
                stock_id = s_doc["_id"]
                market_id = s_doc.get("market_id")
                industry_id = s_doc.get("industry_id")
            else:
                # Auto-create stock if not found
                hose = db_service.db["dimMarkets"].find_one({"code": "HOSE"})
                market_id = hose["_id"] if hose else None
                new_stock = {
                    "market_id": market_id,
                    "industry_id": None,
                    "symbol": symbol,
                    "company_name": symbol,
                    "status": "ACTIVE",
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                res = db_service.db["dimstocks"].insert_one(new_stock)
                stock_id = res.inserted_id
                logging.info(f"[MongoDB] Tự động tạo Stock mới cho {symbol} (ID: {stock_id})")
        
        # 2. Get data_source_id and market_price_data_url
        resolved_ds_id, market_price_data_url = db_service.get_or_create_stock_data_source(stock_id, symbol)
        if resolved_ds_id:
            stock_data_source_id = resolved_ds_id
    else:
        # If not connected, use the URLs from configs or fallback
        market_price_data_url = item.get("market_price_data_url") or item.get("profile_url") or f"https://finance.vietstock.vn/{slug}.htm"

    # Skip checking/crawling if market_price_data_url is empty/null
    if not market_price_data_url:
        logging.warning(f"  [{symbol}] Missing market_price_data_url -> SKIPPED")
        if settings.save_to_mongodb and db_service.is_connected() and log_id:
            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SKIPPED", "Missing market_price_data_url")
        return {"status": "SKIPPED", "message": "Missing market_price_data_url"}

    # Retrieve or construct trading_stats_url
    trading_stats_url = item.get("trading_stats_url")
    if not trading_stats_url and db_service.is_connected() and stock_id:
        ds = db_service.db["dimStockDataSources"].find_one({"stock_id": stock_id})
        if ds:
            trading_stats_url = ds.get("trade_stats_url", "")
    if not trading_stats_url or "finance.vietstock.vn" not in trading_stats_url:
        trading_stats_url = f"https://finance.vietstock.vn/{symbol.lower()}/thong-ke-giao-dich.htm"

    logging.info(f"=== [{idx}/{symbols_count}] Crawling {symbol} ===")
    
    with VietstockBrowser(timeout=timeout) as browser:
        # 4. Thực hiện crawl
        market, financial = crawl_company(
            symbol=symbol,
            slug=slug,
            browser=browser,
            profile_url=market_price_data_url,
            crawl_financial=settings.enable_financial_data,
        )
        
        # Check for immediate crawl errors (if crawl_company failed completely)
        if market.get("error") or not market.get("is_valid_url"):
            # Raise exception so we can capture it and retry
            raise RuntimeError(market.get("error") or "Không tải được trang profile")
            
        stats = None
        if settings.enable_trading_stats and run_trading_stats:
            stats = crawl_trading_stats(symbol=symbol, browser=browser, trading_stats_url=trading_stats_url)
            if stats and (stats.get("error") or not stats.get("is_valid_url")):
                raise RuntimeError(stats.get("error") or "Không tải được trang trading stats")

        # In kết quả crawl chi tiết lên terminal
        logging.info(f"  [{symbol}] Dữ liệu Market: {market}")
        if settings.enable_financial_data:
            logging.info(f"  [{symbol}] Dữ liệu Financial: {financial}")
        if stats:
            logging.info(f"  [{symbol}] Dữ liệu Trading: {stats}")

        # 5. Lưu MongoDB trực tiếp cho từng stock
        cnt_inserted = 0
        cnt_updated = 0
        cnt_failed = 0
        
        if settings.save_to_mongodb and db_service.is_connected() and log_id:
            # Ghi Market Price
            if market.get("is_valid_url") and not market.get("error"):
                if stats and stats.get("is_valid_url") and not stats.get("error"):
                    market["price_change"] = stats.get("period_price_change_value")
                    market["price_change_percent"] = stats.get("period_price_change_pct")

                status_mp = db_service.save_market_price(market, stock_id, market_id, industry_id, stock_data_source_id)
                if status_mp == "INSERT":
                    cnt_inserted += 1
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SUCCESS", "Thành công")
                elif status_mp == "UPDATE":
                    cnt_updated += 1
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SUCCESS", "Thành công")
                else:
                    cnt_failed += 1
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "FAILED", market.get("error") or "Lưu DB thất bại")
            else:
                cnt_failed += 1
                err_msg = market.get("error") or "Invalid URL"
                db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "FAILED", err_msg)

            # Ghi Financial Statement
            if settings.enable_financial_data:
                if financial.get("is_valid_url") and not financial.get("error"):
                    status_fs = db_service.save_financial_statement(financial, stock_id, stock_data_source_id)
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "QUARTERLY_FINANCIAL_STATEMENT", "SUCCESS", "Thành công")
                else:
                    err_msg = financial.get("error") or "Invalid URL"
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "QUARTERLY_FINANCIAL_STATEMENT", "FAILED", err_msg)

            # Ghi BCTT (Financial Report Source) từ stats tab BCTT
            if stats and stats.get("bctt_latest_period") and not stats.get("error"):
                status_rep = db_service.save_financial_report_source(stats, stock_id, stock_data_source_id)
                if status_rep != "SKIPPED":
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "FINANCIAL_REPORT_SOURCE", "SUCCESS", "Thành công BCTT")

        return {
            "status": "SUCCESS",
            "market": market,
            "financial": financial,
            "stats": stats,
            "inserted": cnt_inserted,
            "updated": cnt_updated,
            "failed": cnt_failed
        }


def crawl_symbol_daily_with_timeout(
    item: dict[str, Any],
    idx: int,
    symbols_count: int,
    settings: Any,
    db_service: MongoDBService,
    run_trading_stats: bool,
    data_source_id: ObjectId | None,
    log_id: ObjectId | None,
    timeout: float = 25.0
) -> dict[str, Any]:
    """
    Runs the daily crawl function inside a ThreadPoolExecutor with a hard timeout.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        crawl_single_stock_daily,
        item=item,
        idx=idx,
        symbols_count=symbols_count,
        settings=settings,
        db_service=db_service,
        run_trading_stats=run_trading_stats,
        data_source_id=data_source_id,
        log_id=log_id,
        timeout=timeout
    )
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"Timeout > {timeout}s")
    finally:
        executor.shutdown(wait=False)


def run() -> None:
    """Application entry point used by `run.py`."""
    configure_logging()
    settings = get_settings()
    settings.validate_required()

    # Apply dry_run override
    if settings.dry_run:
        logging.info("🔍 DRY RUN MODE ENABLED – sẽ không lưu dữ liệu vào database hay Google Sheets")
        settings = settings.__class__(
            **{k: v for k, v in settings.__dict__.items() if k not in {'save_to_mongodb', 'save_to_gsheet'}},
            save_to_mongodb=False,
            save_to_gsheet=False
        )

    # 1. Khởi tạo MongoDB Service
    db_service = MongoDBService()
    configs: List[Dict[str, Any]] = []

    # 2. Load configurations (danh sách stocks cần crawl)
    if settings.load_config_from_mongodb and db_service.is_connected():
        configs = db_service.load_stock_configs()

    if not configs and settings.save_to_gsheet:
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(settings.google_sheet_id)
            configs = read_config(spreadsheet)
            logging.info("[GSheet] Đã load configs thành công từ Google Sheets CONFIG.")
        except Exception as e:
            logging.error(f"[GSheet] Load configs từ Google Sheets thất bại: {e}")

    # Fallback cuối cùng nếu không tìm thấy stock nào
    if not configs:
        logging.warning("Không tìm thấy cấu hình stocks từ MongoDB hoặc Google Sheets. Sử dụng cấu hình mặc định để test.")
        # Default stocks fallback
        default_symbols = ["FPT", "HPG", "VNM", "VIC", "TCB"]
        for sym in default_symbols:
            slug = sym.lower()
            configs.append({
                "symbol": sym,
                "slug": slug,
                "company_name_vi": f"Công ty Cổ phần {sym}",
                "profile_url": f"https://finance.vietstock.vn/{slug}/ho-so-doanh-nghiep.htm",
                "trading_stats_url": f"https://finance.vietstock.vn/{slug}/thong-ke-giao-dich.htm",
                "stock_id": None,
                "market_id": None,
                "industry_id": None
            })

    symbols_count = len([x for x in configs if clean_config_text(x.get("symbol"))])
    if settings.crawl_limit > 0:
        configs = configs[:settings.crawl_limit]
        symbols_count = len(configs)
        logging.info(f"🔧 Cấu hình giới hạn crawl: chỉ crawl {symbols_count} mã đầu tiên (CRAWL_LIMIT={settings.crawl_limit})")

    logging.info(f"Bắt đầu crawl cho {symbols_count} mã cổ phiếu.")

    # 3. Tạo crawl log trong MongoDB
    log_id = None
    data_source_id = None
    if settings.save_to_mongodb and db_service.is_connected():
        log_id = db_service.create_crawl_log()
        data_source_id = db_service.get_data_source_id("vietstock")
        logging.info(f"[MongoDB] Khởi tạo crawl log ID: {log_id}")

    # Cấu hình Google Sheets nếu lưu GSheet
    spreadsheet = None
    market_sheet_name = ""
    preliminary_quarter_suffix = ""
    preliminary_financial_sheet_name = ""
    preliminary_trading_sheet_name = ""
    run_trading_stats = settings.enable_trading_stats

    if settings.save_to_gsheet:
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(settings.google_sheet_id)
            market_sheet_name = dated_sheet_name("MARKET_DATA")
            preliminary_quarter_suffix = parse_quarter_suffix(settings.quarter_sheet_override) or latest_completed_quarter_suffix()
            preliminary_financial_sheet_name = output_sheet_name("FINANCIAL_DATA", preliminary_quarter_suffix) if settings.enable_financial_data else ""
            preliminary_trading_sheet_name = output_sheet_name("TRADING_STATS", preliminary_quarter_suffix) if settings.enable_trading_stats else ""

            current_run_index = get_daily_run_index(spreadsheet, market_sheet_name, symbols_count)
            run_trading_stats = should_run_trading_stats_today(
                spreadsheet,
                preliminary_trading_sheet_name,
                current_run_index,
                symbols_count,
            ) if settings.enable_trading_stats else False
        except Exception as e:
            logging.error(f"[GSheet] Cấu hình Google Sheets thất bại: {e}. Tắt lưu GSheet.")
            # fallback
            settings = settings.__class__(
                **{k: v for k, v in settings.__dict__.items() if k != 'save_to_gsheet'},
                save_to_gsheet=False
            )

    market_records: List[Dict[str, Any]] = []
    financial_records: List[Dict[str, Any]] = []
    trading_records: List[Dict[str, Any]] = []

    # Tracking states
    success_first: List[str] = []
    success_retry: List[str] = []
    failed_retry: List[str] = []
    skipped_list: List[str] = []
    
    retry_symbols: List[Dict[str, Any]] = []

    # Biến thống kê log
    records_fetched = 0
    records_inserted = 0
    records_updated = 0
    records_failed = 0
    records_skipped = 0

    # Main Queue Execution
    for idx, item in enumerate(configs, start=1):
        symbol = clean_config_text(item.get("symbol")).upper()
        if not symbol:
            continue

        start_time = time.time()
        try:
            result = crawl_symbol_daily_with_timeout(
                item=item,
                idx=idx,
                symbols_count=symbols_count,
                settings=settings,
                db_service=db_service,
                run_trading_stats=run_trading_stats,
                data_source_id=data_source_id,
                log_id=log_id,
                timeout=settings.symbol_crawl_timeout
            )
            if result["status"] == "SUCCESS":
                success_first.append(symbol)
                market_records.append(result["market"])
                if settings.enable_financial_data:
                    financial_records.append(result["financial"])
                if result["stats"]:
                    trading_records.append(result["stats"])

                records_fetched += 1
                records_inserted += result.get("inserted", 0)
                records_updated += result.get("updated", 0)
                records_failed += result.get("failed", 0)
            elif result["status"] == "SKIPPED":
                skipped_list.append(symbol)
                records_skipped += 1

        except Exception as exc:
            execution_time = time.time() - start_time
            err_msg = str(exc)
            if isinstance(exc, TimeoutError) or "Timeout >" in err_msg:
                logging.warning(f"  [{symbol}] TIMEOUT after {execution_time:.1f}s")
                reason = "timeout"
            else:
                logging.warning(f"  [{symbol}] ERROR after {execution_time:.1f}s: {err_msg}")
                reason = err_msg

            retry_symbols.append({
                "symbol": symbol,
                "reason": reason,
                "attempt": 2,
                "item": item
            })

        if settings.request_delay_seconds > 0 and idx < symbols_count:
            time.sleep(settings.request_delay_seconds)

    # Retry Phase
    if retry_symbols:
        logging.info("\n" + "═" * 70)
        logging.info("=== RETRY PHASE START ===")
        logging.info("═" * 70 + "\n")

        while retry_symbols:
            retry_item = retry_symbols.pop(0)
            symbol = retry_item["symbol"]
            attempt = retry_item["attempt"]
            item = retry_item["item"]
            reason = retry_item["reason"]
            stock_id = item.get("stock_id")

            logging.info(f"[{symbol}] Retry {attempt}/3")

            start_time = time.time()
            try:
                result = crawl_symbol_daily_with_timeout(
                    item=item,
                    idx=attempt,
                    symbols_count=3,
                    settings=settings,
                    db_service=db_service,
                    run_trading_stats=run_trading_stats,
                    data_source_id=data_source_id,
                    log_id=log_id,
                    timeout=settings.symbol_crawl_timeout
                )
                if result["status"] == "SUCCESS":
                    success_retry.append(symbol)
                    market_records.append(result["market"])
                    if settings.enable_financial_data:
                        financial_records.append(result["financial"])
                    if result["stats"]:
                        trading_records.append(result["stats"])

                    records_fetched += 1
                    records_inserted += result.get("inserted", 0)
                    records_updated += result.get("updated", 0)
                    records_failed += result.get("failed", 0)
                    logging.info(f"  [{symbol}] Retried SUCCESS on attempt {attempt}")
                elif result["status"] == "SKIPPED":
                    skipped_list.append(symbol)
                    logging.info(f"  [{symbol}] Retried SKIPPED on attempt {attempt}")

            except Exception as exc:
                execution_time = time.time() - start_time
                err_msg = str(exc)
                if isinstance(exc, TimeoutError) or "Timeout >" in err_msg:
                    logging.warning(f"  [{symbol}] TIMEOUT after {execution_time:.1f}s")
                    new_reason = "timeout"
                else:
                    logging.warning(f"  [{symbol}] ERROR after {execution_time:.1f}s: {err_msg}")
                    new_reason = err_msg

                if attempt < 3:
                    logging.warning(f"  [{symbol}] Attempt {attempt} failed ({new_reason}), will retry again")
                    retry_symbols.append({
                        "symbol": symbol,
                        "reason": new_reason,
                        "attempt": attempt + 1,
                        "item": item
                    })
                else:
                    failed_retry.append(symbol)
                    logging.error(f"  [{symbol}] FAILED AFTER 3 RETRIES")
                    records_failed += 1
                    if settings.save_to_mongodb and db_service.is_connected() and log_id:
                        db_service.write_crawl_log_detail(log_id, stock_id, symbol, "CRAWL_JOB", "FAILED", f"FAILED AFTER 3 RETRIES: {new_reason}")

            if settings.request_delay_seconds > 0 and len(retry_symbols) > 0:
                time.sleep(settings.request_delay_seconds)

    # 6b. Market overview (KQGD) — cùng nhịp daily với market price khi bật MongoDB
    market_overview_failed = False
    if (
        settings.enable_daily_market_overview
        and settings.save_to_mongodb
        and db_service.is_connected()
    ):
        try:
            from vietstock_crawler.jobs.market_overview_daily import run_daily_market_overview

            result = run_daily_market_overview(db_service)
            if result and result.get("status") == "FAILED":
                market_overview_failed = True
        except Exception as exc:
            market_overview_failed = True
            logging.error("[MarketOverview] Job failed: %s", exc, exc_info=True)

    # 6. Ghi logs tổng hợp cuối cùng & chất lượng
    ended_at = datetime.utcnow()
    status_summary = "SUCCESS" if records_failed == 0 else "PARTIAL_SUCCESS"
    if records_fetched == 0 and records_skipped == 0 and records_failed == 0:
        status_summary = "FAILED"
    elif records_fetched == records_failed and records_fetched > 0:
        status_summary = "FAILED"

    # Nếu crawl market overview bị lỗi thì set trạng thái tổng phù hợp là PARTIAL_SUCCESS
    if market_overview_failed:
        if status_summary == "SUCCESS":
            status_summary = "PARTIAL_SUCCESS"
            logging.info("[MarketOverview] Set overall job status to PARTIAL_SUCCESS due to market overview failure.")

    if settings.save_to_mongodb and db_service.is_connected() and log_id:
        error_msg = f"Skipped: {records_skipped} mã đã có dữ liệu" if records_skipped > 0 else ""
        if market_overview_failed:
            error_msg = (error_msg + "; " if error_msg else "") + "Market overview crawl failed"

        db_service.update_crawl_log(
            log_id=log_id,
            ended_at=ended_at,
            status=status_summary,
            records_fetched=records_fetched,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            error_message=error_msg
        )
        db_service.write_crawl_quality(
            log_id=log_id,
            data_source_id=data_source_id,
            records_fetched=records_fetched,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed,
            status=status_summary
        )
        logging.info("[MongoDB] Đã cập nhật xong CrawlLog và CrawlQuality.")

    # 7. Lưu Google Sheets (nếu được bật)
    if settings.save_to_gsheet and spreadsheet:
        try:
            final_quarter_suffix = preliminary_quarter_suffix
            financial_sheet_name = preliminary_financial_sheet_name
            trading_sheet_name = preliminary_trading_sheet_name

            if settings.create_quarterly_financial_trading_sheets and (settings.enable_financial_data or (settings.enable_trading_stats and run_trading_stats)):
                if settings.use_latest_reported_quarter_for_sheets:
                    final_quarter_suffix = resolve_latest_reported_quarter_suffix(financial_records, trading_records)
                financial_sheet_name = output_sheet_name("FINANCIAL_DATA", final_quarter_suffix) if settings.enable_financial_data else ""
                trading_sheet_name = output_sheet_name("TRADING_STATS", final_quarter_suffix) if settings.enable_trading_stats else ""
            elif not settings.create_quarterly_financial_trading_sheets:
                financial_sheet_name = dated_sheet_name("FINANCIAL_DATA") if settings.enable_financial_data else ""
                trading_sheet_name = dated_sheet_name("TRADING_STATS") if settings.enable_trading_stats else ""
                final_quarter_suffix = ""

            append_records_with_titles(spreadsheet, market_sheet_name, market_records, MARKET_COLUMNS)

            if settings.enable_financial_data and financial_sheet_name and financial_records:
                append_records_with_titles(spreadsheet, financial_sheet_name, financial_records, FINANCIAL_COLUMNS)

            if settings.enable_trading_stats and run_trading_stats and trading_sheet_name and trading_records:
                append_records_with_titles(spreadsheet, trading_sheet_name, trading_records, TRADING_STATS_COLUMNS)

            logging.info("[GSheet] Đã ghi records lên Google Sheets thành công.")
        except Exception as e:
            logging.error(f"[GSheet] Lưu dữ liệu lên Google Sheets thất bại: {e}")

    logging.info("\n=================================================")
    logging.info("CRAWL SUMMARY")
    logging.info("=============\n")
    logging.info(f"Total symbols: {symbols_count}")
    logging.info(f"Success: {len(success_first)}")
    logging.info(f"Retried Success: {len(success_retry)}")
    logging.info(f"Failed After Retry: {len(failed_retry)}")
    logging.info("=====================\n")
    if failed_retry:
        logging.info("Failed symbols:\n")
        for fs in failed_retry:
            logging.info(f"* {fs}")
    else:
        logging.info("No failed symbols.")
    logging.info("\n" + "═" * 70)

    logging.info(
        f"\n=== Kết quả crawl: ===\n"
        f"- Tổng số mã: {records_fetched + records_skipped}\n"
        f"- Thêm mới (Insert DB): {records_inserted}\n"
        f"- Cập nhật (Update DB): {records_updated}\n"
        f"- Bỏ qua (Skipped): {records_skipped}\n"
        f"- Thất bại (Failed): {records_failed}\n"
        f"- Trạng thái: {status_summary}\n"
    )
