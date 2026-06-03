import logging
import os
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run():
    # 1. Load env từ services/crawler/.env
    # File .env ở cùng thư mục với script này
    load_dotenv()
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        logging.error("Không tìm thấy MONGODB_URI trong file .env")
        return

    try:
        client = MongoClient(mongodb_uri)
        db = client.get_default_database()
        logging.info(f"Đã kết nối MongoDB. Database: {db.name}")

        # 2. Lấy market_id của sàn HOSE
        market_col = db["dimMarkets"]
        hose_market = market_col.find_one({"code": "HOSE"})
        if not hose_market:
            # Tạo HOSE market nếu chưa có
            hose_doc = {
                "code": "HOSE",
                "name": "Ho Chi Minh Stock Exchange",
                "country": "Vietnam",
                "timezone": "Asia/Ho_Chi_Minh",
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            res = market_col.insert_one(hose_doc)
            market_id = res.inserted_id
            logging.info(f"Đã tạo market HOSE (ID: {market_id})")
        else:
            market_id = hose_market["_id"]
            logging.info(f"Market HOSE ID: {market_id}")

        # 3. Lấy danh sách từ vnstock
        from vnstock import Listing
        l = Listing()
        df = l.symbols_by_exchange('HOSE')
        hose_df = df[(df['exchange'] == 'HOSE') & (df['type'] == 'stock')]
        logging.info(f"Lấy thành công {len(hose_df)} mã cổ phiếu sàn HOSE từ vnstock.")

        # 4. Upsert vào dimstocks
        stock_col = db["dimstocks"]
        
        inserted_count = 0
        updated_count = 0

        for _, row in hose_df.iterrows():
            symbol = row['symbol'].upper()
            organ_name = row['organ_name']
            
            # Slug Vietstock chuẩn: <SYMBOL>/ho-so-doanh-nghiep
            slug = f"{symbol}/ho-so-doanh-nghiep"

            query = {"symbol": symbol}
            
            # Dữ liệu cập nhật/chèn mới
            stock_data = {
                "market_id": market_id,
                "symbol": symbol,
                "company_name": organ_name,
                "exchange_code": "HOSE",
                "status": "ACTIVE",
                "slug": slug,
                "updated_at": datetime.utcnow()
            }

            existing = stock_col.find_one(query)
            if existing:
                # Chỉ update nếu slug chưa có hoặc tên công ty thay đổi
                if not existing.get("slug") or existing.get("company_name") != organ_name:
                    stock_col.update_one(query, {"$set": {"slug": slug, "company_name": organ_name, "updated_at": datetime.utcnow()}})
                    updated_count += 1
            else:
                # Chèn mới
                stock_data["created_at"] = datetime.utcnow()
                stock_col.insert_one(stock_data)
                inserted_count += 1

        logging.info(f"Hoàn thành seed stocks: Thêm mới: {inserted_count}, Cập nhật: {updated_count}")
        client.close()
        
    except Exception as e:
        logging.exception(f"Lỗi khi seed stocks: {e}")

if __name__ == "__main__":
    run()
