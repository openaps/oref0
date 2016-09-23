
import json
# http://blog.codevariety.com/2012/01/06/python-serializing-dates-datetime-datetime-into-json/
def date_handler(obj):
    return obj.isoformat() if hasattr(obj, 'isoformat') else obj

def serialize (blob, reporter):
  return json.dumps(blob, indent=2, default=date_handler)
