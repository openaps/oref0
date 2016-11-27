
class Registry (object):
  def __init__ (self):
    self.__USES__ = { }

  def get_uses (self, device, config):
    all_uses = self.__USES__.values( )
    all_uses.sort(key=lambda usage: getattr(usage, 'sortOrder', usage.__name__))
    return all_uses

  def __call__ (self):
    def decorator (cls):
      if cls.__name__ not in self.__USES__:
        self.__USES__[cls.__name__] = cls
      return cls
    return decorator

