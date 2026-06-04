import os
from dotenv import load_dotenv
from pymongo import MongoClient
import json
from bson import ObjectId

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        import datetime
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)

load_dotenv()
uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)
db = client.get_default_database()

print("--- dimstocks Sample ---")
for doc in db["dimstocks"].find().limit(2):
    print(json.dumps(doc, cls=JSONEncoder, ensure_ascii=True))

print("\n--- dimStockDataSources Sample ---")
for doc in db["dimStockDataSources"].find().limit(5):
    print(json.dumps(doc, cls=JSONEncoder, ensure_ascii=True))
