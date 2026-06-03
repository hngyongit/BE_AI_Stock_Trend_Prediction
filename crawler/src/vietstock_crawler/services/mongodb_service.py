from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.results import InsertOneResult

from vietstock_crawler.config.settings import get_settings
from vietstock_crawler.utils.date_utils import now_vn

logger = logging.getLogger(__name__)


class MongoDBService:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self.db = None
        if self.settings.save_to_mongodb or self.settings.load_config_from_mongodb:
            try:
                self.client = MongoClient(self.settings.mongodb_uri)
                self.db = self.client.get_default_database()
                logger.info(f"Đã kết nối MongoDB thành công. Database hiện tại: {self.db.name}")
            except Exception as e:
                logger.exception("Kết nối MongoDB thất bại")
                self.client = None
                self.db = None

    def is_connected(self) -> bool:
        return self.db is not None

    def get_data_source_id(self, name: str = "vietstock") -> Optional[ObjectId]:
        if not self.is_connected():
            return None
        col = self.db["dimDataSources"]
        ds = col.find_one({"name": name})
        if ds:
            return ds["_id"]
        # Nếu chưa có thì tự động tạo mới data source 'vietstock'
        new_ds = {
            "name": name,
            "provider_type": "crawler",
            "base_url": "https://finance.vietstock.vn",
            "description": "Vietstock Finance crawler",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        res = col.insert_one(new_ds)
        logger.info(f"[MongoDB] Tự động tạo data source: {name} (ID: {res.inserted_id})")
        return res.inserted_id

    def load_stock_configs(self) -> List[Dict[str, str]]:
        if not self.is_connected():
            logger.warning("[MongoDB] Không có kết nối DB. Không thể load configs.")
            return []

        col = self.db["dimstocks"]
        stocks = list(col.find({"status": "ACTIVE"}))
        if not stocks:
            # Fallback nếu dimstocks chưa được seeded
            logger.warning("[MongoDB] Không tìm thấy stock active nào trong collection dimstocks.")
            return []

        configs = []
        for s in stocks:
            symbol = s.get("symbol", "").upper()
            if not symbol:
                continue
            # Slug mặc định trong Vietstock là chữ thường của symbol
            # Ví dụ: FPT -> fpt
            slug = s.get("slug", symbol.lower())
            configs.append({
                "symbol": symbol,
                "slug": slug,
                "company_name_vi": s.get("company_name", ""),
                "profile_url": f"https://finance.vietstock.vn/{slug}/ho-so-doanh-nghiep.htm",
                "trading_stats_url": f"https://finance.vietstock.vn/{slug}/thong-ke-giao-dich.htm",
                "stock_id": s["_id"],
                "market_id": s.get("market_id"),
                "industry_id": s.get("industry_id")
            })
        
        logger.info(f"[MongoDB] Đã load {len(configs)} stocks config từ database.")
        return configs

    def create_crawl_log(self) -> Optional[ObjectId]:
        if not self.is_connected():
            return None
        col = self.db["crawlLogs"]
        log_doc = {
            "crawl_job_id": None,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "status": "PENDING",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_failed": 0,
            "error_message": "",
            "created_at": datetime.utcnow()
        }
        res = col.insert_one(log_doc)
        return res.inserted_id

    def update_crawl_log(self, log_id: ObjectId, ended_at: datetime, status: str, 
                         records_fetched: int, records_inserted: int, records_updated: int, 
                         records_failed: int, error_message: str = ""):
        if not self.is_connected() or not log_id:
            return
        col = self.db["crawlLogs"]
        col.update_one(
            {"_id": log_id},
            {
                "$set": {
                    "ended_at": ended_at,
                    "status": status,
                    "records_fetched": records_fetched,
                    "records_inserted": records_inserted,
                    "records_updated": records_updated,
                    "records_failed": records_failed,
                    "error_message": error_message
                }
            }
        )

    def write_crawl_log_detail(self, log_id: ObjectId, stock_id: Optional[ObjectId], symbol: str,
                               data_type: str, status: str, message: str):
        if not self.is_connected() or not log_id:
            return
        col = self.db["crawlLogDetails"]
        detail_doc = {
            "crawl_log_id": log_id,
            "stock_id": stock_id,
            "symbol": symbol,
            "data_type": data_type,
            "status": status,
            "message": message,
            "created_at": datetime.utcnow()
        }
        col.insert_one(detail_doc)

    def write_crawl_quality(self, log_id: ObjectId, data_source_id: ObjectId, 
                            records_fetched: int, records_inserted: int, 
                            records_updated: int, records_failed: int, status: str):
        if not self.is_connected() or not log_id:
            return
        col = self.db["factCrawlQualities"]
        
        # Lấy market_id mặc định từ market HOSE
        market_col = self.db["dimMarkets"]
        hose_market = market_col.find_one({"code": "HOSE"})
        market_id = hose_market["_id"] if hose_market else None

        # time_id hiện tại
        time_id = int(datetime.utcnow().strftime("%Y%m%d"))

        success_rate = 0.0
        if records_fetched > 0:
            success_rate = round((records_inserted + records_updated) / records_fetched * 100, 2)

        quality_doc = {
            "crawl_job_id": None,
            "data_source_id": data_source_id,
            "market_id": market_id,
            "time_id": time_id,
            "records_fetched": records_fetched,
            "records_inserted": records_inserted,
            "records_updated": records_updated,
            "records_failed": records_failed,
            "success_rate": success_rate,
            "status": status,
            "created_at": datetime.utcnow()
        }
        col.insert_one(quality_doc)

    def save_market_price(self, record: Dict[str, Any], stock_id: ObjectId, market_id: ObjectId,
                          industry_id: Optional[ObjectId], data_source_id: ObjectId) -> str:
        """
        Ghi dữ liệu market price vào factMarketPrices.
        Trả về "INSERT", "UPDATE" hoặc "FAILED"
        """
        if not self.is_connected():
            return "FAILED"

        col = self.db["factMarketPrices"]
        
        # 1. Parse time_id
        # Snapshot_at có dạng VN time string: "2026-06-03 17:00:00" -> ta chuyển thành YYYYMMDD
        snapshot_str = record.get("snapshot_at", "")
        try:
            dt = datetime.strptime(snapshot_str.split()[0], "%Y-%m-%d")
            time_id = int(dt.strftime("%Y%m%d"))
        except Exception:
            # Fallback ngày hiện tại
            time_id = int(datetime.utcnow().strftime("%Y%m%d"))

        # 2. Chuẩn hóa các trường số
        def clean_num(val):
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        price_doc = {
            "stock_id": stock_id,
            "market_id": market_id,
            "industry_id": industry_id,
            "data_source_id": data_source_id,
            "time_id": time_id,

            "open_price": clean_num(record.get("open")),
            "high_price": clean_num(record.get("high")),
            "low_price": clean_num(record.get("low")),
            "close_price": clean_num(record.get("close")),
            "volume": clean_num(record.get("volume")),

            "bid_volume": clean_num(record.get("bid_volume")),
            "ask_volume": clean_num(record.get("ask_volume")),
            "foreign_buy": clean_num(record.get("foreign_buy")),
            "foreign_sell": clean_num(record.get("foreign_sell")),
            "foreign_net": clean_num(record.get("foreign_net")),

            "market_cap": clean_num(record.get("market_cap")),
            "eps": clean_num(record.get("eps")),
            "pe": clean_num(record.get("pe")),
            "forward_pe": clean_num(record.get("forward_pe")),
            "bvps": clean_num(record.get("bvps")),
            "pb": clean_num(record.get("pb")),
            "beta": clean_num(record.get("beta")),
            "roe": clean_num(record.get("roe")),
            "ros": clean_num(record.get("ros")),
            "roaa": clean_num(record.get("roaa")),

            "price_change": clean_num(record.get("price_change")),
            "price_change_percent": clean_num(record.get("price_change_percent")),

            "crawled_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }

        # Kiểm tra sự tồn tại của record trùng (stock_id, time_id, data_source_id)
        query = {
            "stock_id": stock_id,
            "time_id": time_id,
            "data_source_id": data_source_id
        }

        existing = col.find_one(query)
        if existing:
            # Update
            # Bỏ field created_at khi update để giữ ngày tạo ban đầu
            price_doc.pop("created_at", None)
            col.update_one(query, {"$set": price_doc})
            logger.info(f"[MongoDB] Updated market price for {record.get('symbol')} on {time_id}")
            return "UPDATE"
        else:
            # Insert
            col.insert_one(price_doc)
            logger.info(f"[MongoDB] Inserted market price for {record.get('symbol')} on {time_id}")
            return "INSERT"

    def save_financial_statement(self, record: Dict[str, Any], stock_id: ObjectId, 
                                 data_source_id: ObjectId) -> str:
        """
        Ghi dữ liệu báo cáo tài chính vào fact_financial_statements (collection: factFinancialStatements).
        Trả về "INSERT", "UPDATE" hoặc "FAILED"
        """
        if not self.is_connected():
            return "FAILED"

        col = self.db["factFinancialStatements"]

        # 1. Parse report_period_id từ BCTT latest period hoặc snapshot_at
        # BCTT latest period có dạng ví dụ: "Q1/2026" hoặc "2026-Q1"
        latest_period = record.get("bctt_latest_period") or record.get("latest_period") or ""
        fiscal_year = None
        fiscal_quarter = None

        if "/" in latest_period:
            parts = latest_period.split("/")
            if len(parts) == 2:
                q_part = parts[0].strip().upper()
                if "Q" in q_part:
                    try:
                        fiscal_quarter = int(q_part.replace("Q", ""))
                        fiscal_year = int(parts[1].strip())
                    except ValueError:
                        pass
        elif "-" in latest_period:
            parts = latest_period.split("-")
            if len(parts) == 2:
                # 2026-Q1 hoặc Q1-2026
                p0 = parts[0].strip()
                p1 = parts[1].strip()
                if "Q" in p0.upper():
                    try:
                        fiscal_quarter = int(p0.upper().replace("Q", ""))
                        fiscal_year = int(p1)
                    except ValueError:
                        pass
                elif "Q" in p1.upper():
                    try:
                        fiscal_quarter = int(p1.upper().replace("Q", ""))
                        fiscal_year = int(p0)
                    except ValueError:
                        pass

        if not fiscal_year or not fiscal_quarter:
            # Fallback nếu không parse được: Lấy năm hiện tại và quý hiện tại
            now = datetime.utcnow()
            fiscal_year = now.year
            fiscal_quarter = (now.month - 1) // 3 + 1

        # 2. Tìm hoặc tạo report_period_id
        period_col = self.db["dimReportPeriods"]
        period_name = f"Q{fiscal_quarter}/{fiscal_year}"
        period = period_col.find_one({"fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter})
        if period:
            report_period_id = period["_id"]
        else:
            new_period = {
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "period_name": period_name,
                "period_start_date": None,
                "period_end_date": None,
                "is_latest": True,
                "created_at": datetime.utcnow()
            }
            # Set các period cũ thành is_latest = False
            period_col.update_many({}, {"$set": {"is_latest": False}})
            res = period_col.insert_one(new_period)
            report_period_id = res.inserted_id
            logger.info(f"[MongoDB] Tự động tạo report period mới: {period_name}")

        def clean_num(val):
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        fin_doc = {
            "stock_id": stock_id,
            "report_period_id": report_period_id,
            "data_source_id": data_source_id,

            "net_revenue": clean_num(record.get("net_revenue")),
            "gross_profit": clean_num(record.get("gross_profit")),
            "net_profit_from_operating_activities": clean_num(record.get("net_profit_from_operating_activity")),
            "corporate_income_tax": clean_num(record.get("corporate_income_tax")),
            
            "net_interest_income": clean_num(record.get("net_interest_income")),
            "operating_expense": clean_num(record.get("operating_expense")),
            "total_operating_income": clean_num(record.get("total_operating_income")),

            "profit_before_tax": clean_num(record.get("profit_before_tax")),
            "profit_after_tax": clean_num(record.get("profit_after_tax")),
            "parent_company_profit": clean_num(record.get("parent_company_profit")),

            "current_assets": clean_num(record.get("current_assets")),
            "total_assets": clean_num(record.get("total_assets")),
            "customer_loans": clean_num(record.get("customer_loans")),
            "customer_deposits": clean_num(record.get("customer_deposits")),
            "liabilities": clean_num(record.get("liabilities")),
            "current_liabilities": clean_num(record.get("current_liabilities")),
            "equity": clean_num(record.get("equity")),
            "retained_earnings": clean_num(record.get("retained_earnings")),

            "eps": clean_num(record.get("eps_4q")),
            "pe": clean_num(record.get("pe_basic")),
            "forward_pe": None, # Không crawl được từ financial sheet trực tiếp
            "bvps": clean_num(record.get("bvps")),
            "pb": None,
            "beta": None,
            "ros": clean_num(record.get("ros")),
            "roe": clean_num(record.get("roe")),
            "roaa": clean_num(record.get("roaa")),

            "crawled_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }

        query = {
            "stock_id": stock_id,
            "report_period_id": report_period_id,
            "data_source_id": data_source_id
        }

        existing = col.find_one(query)
        if existing:
            fin_doc.pop("created_at", None)
            col.update_one(query, {"$set": fin_doc})
            logger.info(f"[MongoDB] Updated financial statement for stock_id {stock_id} on {period_name}")
            return "UPDATE"
        else:
            col.insert_one(fin_doc)
            logger.info(f"[MongoDB] Inserted financial statement for stock_id {stock_id} on {period_name}")
            return "INSERT"

    def save_financial_report_source(self, record: Dict[str, Any], stock_id: ObjectId, 
                                     data_source_id: ObjectId) -> str:
        """
        Ghi dữ liệu báo cáo tài chính gốc từ tab BCTT vào factFinancialReportSources
        (collection: factFinancialReportSources).
        Trả về "INSERT", "UPDATE" hoặc "FAILED"
        """
        if not self.is_connected():
            return "FAILED"

        col = self.db["factFinancialReportSources"]

        # 1. Parse report_period_id
        latest_period = record.get("bctt_latest_period") or ""
        fiscal_year = None
        fiscal_quarter = None

        if "/" in latest_period:
            parts = latest_period.split("/")
            if len(parts) == 2:
                q_part = parts[0].strip().upper()
                if "Q" in q_part:
                    try:
                        fiscal_quarter = int(q_part.replace("Q", ""))
                        fiscal_year = int(parts[1].strip())
                    except ValueError:
                        pass

        if not fiscal_year or not fiscal_quarter:
            now = datetime.utcnow()
            fiscal_year = now.year
            fiscal_quarter = (now.month - 1) // 3 + 1

        period_col = self.db["dimReportPeriods"]
        period_name = f"Q{fiscal_quarter}/{fiscal_year}"
        period = period_col.find_one({"fiscal_year": fiscal_year, "fiscal_quarter": fiscal_quarter})
        if period:
            report_period_id = period["_id"]
        else:
            new_period = {
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "period_name": period_name,
                "period_start_date": None,
                "period_end_date": None,
                "is_latest": True,
                "created_at": datetime.utcnow()
            }
            period_col.update_many({}, {"$set": {"is_latest": False}})
            res = period_col.insert_one(new_period)
            report_period_id = res.inserted_id

        # Chỉ insert nếu có dữ liệu BCTT
        if not record.get("bctt_net_revenue") and not record.get("bctt_gross_profit"):
            return "SKIPPED"

        def clean_num(val):
            if val is None or val == "":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        source_url = record.get("bctt_source") or record.get("source") or ""

        report_doc = {
            "stock_id": stock_id,
            "report_period_id": report_period_id,
            "data_source_id": data_source_id,
            "source_url": source_url,
            "is_valid_url": record.get("bctt_is_valid_url", True),
            "report_file_type": "HTML",
            "report_status": "crawled",

            "bctt_net_revenue": clean_num(record.get("bctt_net_revenue")),
            "bctt_cost_of_goods_sold": clean_num(record.get("bctt_cost_of_goods_sold")),
            "bctt_gross_profit": clean_num(record.get("bctt_gross_profit")),
            "bctt_financial_income": clean_num(record.get("bctt_financial_income")),
            "bctt_financial_expense": clean_num(record.get("bctt_financial_expense")),
            "bctt_selling_expense": clean_num(record.get("bctt_selling_expense")),
            "bctt_admin_expense": clean_num(record.get("bctt_admin_expense")),
            "bctt_net_operating_profit": clean_num(record.get("bctt_net_operating_profit")),
            "bctt_other_profit": clean_num(record.get("bctt_other_profit")),
            "bctt_associate_jv_profit": clean_num(record.get("bctt_associate_jv_profit")),
            "bctt_profit_before_tax": clean_num(record.get("bctt_profit_before_tax")),
            "bctt_profit_after_tax": clean_num(record.get("bctt_profit_after_tax")),
            "bctt_parent_company_profit": clean_num(record.get("bctt_parent_company_profit")),
            "bctt_basic_eps": clean_num(record.get("bctt_basic_eps")),

            "crawled_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }

        query = {
            "stock_id": stock_id,
            "report_period_id": report_period_id,
            "source_url": source_url
        }

        # Nếu không có source_url thì dùng query theo stock_id + report_period_id + data_source_id
        if not source_url:
            query = {
                "stock_id": stock_id,
                "report_period_id": report_period_id,
                "data_source_id": data_source_id
            }

        existing = col.find_one(query)
        if existing:
            report_doc.pop("created_at", None)
            col.update_one(query, {"$set": report_doc})
            logger.info(f"[MongoDB] Updated financial report source for stock_id {stock_id} on {period_name}")
            return "UPDATE"
        else:
            col.insert_one(report_doc)
            logger.info(f"[MongoDB] Inserted financial report source for stock_id {stock_id} on {period_name}")
            return "INSERT"
