
class DataContext:

    def __init__(self, **kwargs) -> None:
        self.__data = {}

    def get(self, key: str):
        return self.__data.get(key, None)
    
    def set(self, key: str, value) -> None:
        self.__data[key] = value

    def has(self, key: str) -> bool:
        return key in self.__data
    
    def delete(self, key: str) -> None:
        if key in self.__data:
            del self.__data[key]
    
    def clear(self) -> None:
        self.__data.clear()

    def keys(self):
        return self.__data.keys()
    
    def values(self):
        return self.__data.values()
    
    def items(self):
        return self.__data.items()