from pymongo import MongoClient
import json
import time

import datetime
from bson import json_util
from pytz import timezone


db_uri = 'mongodb://user:pass@ds135003.mlab.com:35003'
db_name = 'heroku_b6k1n0tj'
collection_name = 'devicestatus'

time_now = datetime.datetime.now()
time_to_delete = datetime.datetime.now() - datetime.timedelta(days=60)

datetime_obj_pacific = time_to_delete.astimezone(timezone('UTC'))

two_month_ago = datetime_obj_pacific.strftime("%Y-%m-%dT%H:%M:%S")+'.000Z'
print('Deleting objects older than', two_month_ago)


client = MongoClient(db_uri+ '/'+ db_name + '?socketTimeoutMS=180000&connectTimeoutMS=60000')
db = client[db_name]
collection = db[collection_name]

myquery = {"created_at":  {"$lt": two_month_ago} }


with open("devicestatus_backup.txt", "a") as myfile:
    mydoc = collection.find(myquery)
    for x in mydoc:
      string = json.dumps(x, default=json_util.default)
      myfile.write(string + '\n')
      
res = collection.delete_many(myquery)
print (res.deleted_count, " documents deleted.")
