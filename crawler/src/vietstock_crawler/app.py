from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

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

    # Biến thống kê log
    records_fetched = 0
    records_inserted = 0
    records_updated = 0
    records_failed = 0

    with VietstockBrowser() as browser:
        for idx, item in enumerate(configs, start=1):
            symbol = clean_config_text(item.get("symbol")).upper()
            slug = normalize_slug_value(item.get("slug"))
            
            if not symbol:
                continue

            stock_id = item.get("stock_id")
            market_id = item.get("market_id")
            industry_id = item.get("industry_id")
            
            # Retrieve or create stock data source details from DB if connected
            market_price_data_url = ""
            data_source_id = item.get("data_source_id")
            
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
                data_source_id, market_price_data_url = db_service.get_or_create_stock_data_source(stock_id, symbol)
            else:
                # If not connected, use the URLs from configs or fallback
                market_price_data_url = item.get("market_price_data_url") or item.get("profile_url") or f"https://finance.vietstock.vn/{slug}.htm"
                data_source_id = None

            # Skip checking/crawling if market_price_data_url is empty/null
            if not market_price_data_url:
                logging.warning(f"  [{symbol}] Missing market_price_data_url -> SKIPPED")
                if settings.save_to_mongodb and db_service.is_connected() and log_id:
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SKIPPED", "Missing market_price_data_url")
                continue

            # Retrieve or construct trading_stats_url
            trading_stats_url = item.get("trading_stats_url")
            if not trading_stats_url and db_service.is_connected() and stock_id:
                ds = db_service.db["dimStockDataSources"].find_one({"stock_id": stock_id})
                if ds:
                    trading_stats_url = ds.get("trade_stats_url", "")
            if not trading_stats_url or "finance.vietstock.vn" not in trading_stats_url:
                trading_stats_url = f"https://finance.vietstock.vn/{symbol.lower()}/thong-ke-giao-dich.htm"

            logging.info(f"=== [{idx}/{symbols_count}] Crawling {symbol} ===")
            
            try:
                # 4. Thực hiện crawl
                market, financial = crawl_company(
                    symbol=symbol,
                    slug=slug,
                    browser=browser,
                    profile_url=market_price_data_url,
                    crawl_financial=settings.enable_financial_data,
                )
                
                records_fetched += 1
                
                stats = None
                if settings.enable_trading_stats and run_trading_stats:
                    stats = crawl_trading_stats(symbol=symbol, browser=browser, trading_stats_url=trading_stats_url)

                # Thu thập records cho GSheet (nếu cần)
                market_records.append(market)
                if settings.enable_financial_data:
                    financial_records.append(financial)
                if stats:
                    trading_records.append(stats)

                # In kết quả crawl chi tiết lên terminal
                logging.info(f"  [{symbol}] Dữ liệu Market: {market}")
                if settings.enable_financial_data:
                    logging.info(f"  [{symbol}] Dữ liệu Financial: {financial}")
                if stats:
                    logging.info(f"  [{symbol}] Dữ liệu Trading: {stats}")

                # 5. Lưu MongoDB trực tiếp cho từng stock
                if settings.save_to_mongodb and db_service.is_connected() and log_id:
                    # Ghi Market Price
                    if market.get("is_valid_url") and not market.get("error"):
                        # Trộn thông tin trading stats nếu có vào market record để lưu factMarketPrices đầy đủ
                        # (Theo ERD: fact_market_prices gồm đầy đủ chỉ số định giá, giao dịch, biến động giá)
                        if stats and stats.get("is_valid_url") and not stats.get("error"):
                            # Map các field stats
                            market["price_change"] = stats.get("period_price_change_value")
                            market["price_change_percent"] = stats.get("period_price_change_pct")

                        status_mp = db_service.save_market_price(market, stock_id, market_id, industry_id, data_source_id)
                        if status_mp == "INSERT":
                            records_inserted += 1
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SUCCESS", "Thành công")
                        elif status_mp == "UPDATE":
                            records_updated += 1
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "SUCCESS", "Thành công")
                        else:
                            records_failed += 1
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "FAILED", market.get("error") or "Lưu DB thất bại")
                    else:
                        records_failed += 1
                        err_msg = market.get("error") or "Invalid URL"
                        db_service.write_crawl_log_detail(log_id, stock_id, symbol, "DAILY_MARKET_PRICE", "FAILED", err_msg)

                    # Ghi Financial Statement
                    if settings.enable_financial_data:
                        if financial.get("is_valid_url") and not financial.get("error"):
                            status_fs = db_service.save_financial_statement(financial, stock_id, data_source_id)
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "QUARTERLY_FINANCIAL_STATEMENT", "SUCCESS", "Thành công")
                        else:
                            err_msg = financial.get("error") or "Invalid URL"
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "QUARTERLY_FINANCIAL_STATEMENT", "FAILED", err_msg)

                    # Ghi BCTT (Financial Report Source) từ stats tab BCTT
                    if stats and stats.get("bctt_latest_period") and not stats.get("error"):
                        status_rep = db_service.save_financial_report_source(stats, stock_id, data_source_id)
                        if status_rep != "SKIPPED":
                            db_service.write_crawl_log_detail(log_id, stock_id, symbol, "FINANCIAL_REPORT_SOURCE", "SUCCESS", "Thành công BCTT")

                # Delay giãn cách request tránh bị chặn IP
                time.sleep(settings.request_delay_seconds)

            except Exception as e:
                logging.exception(f"Lỗi crawl symbol {symbol}: {e}")
                records_failed += 1
                if settings.save_to_mongodb and db_service.is_connected() and log_id:
                    db_service.write_crawl_log_detail(log_id, stock_id, symbol, "CRAWL_JOB", "FAILED", str(e))

    # 6. Ghi logs tổng hợp cuối cùng & chất lượng
    ended_at = datetime.utcnow()
    status_summary = "SUCCESS" if records_failed == 0 else "PARTIAL_SUCCESS"
    if records_fetched == records_failed:
        status_summary = "FAILED"

    if settings.save_to_mongodb and db_service.is_connected() and log_id:
        db_service.update_crawl_log(
            log_id=log_id,
            ended_at=ended_at,
            status=status_summary,
            records_fetched=records_fetched,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_failed=records_failed
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

    logging.info(
        f"\n=== Kết quả crawl: ===\n"
        f"- Tổng số mã: {records_fetched}\n"
        f"- Thêm mới (Insert DB): {records_inserted}\n"
        f"- Cập nhật (Update DB): {records_updated}\n"
        f"- Thất bại (Failed): {records_failed}\n"
        f"- Trạng thái: {status_summary}\n"
    )
