from .actions import (
    Base64Decode,
    Base64Encode,
    DictMerge,
    JsonGetPath,
    JsonParse,
    JsonStringify,
    ListUnique,
    RegexExtract,
)

package_name = "data"

actions = [
    JsonParse,
    JsonStringify,
    JsonGetPath,
    RegexExtract,
    Base64Encode,
    Base64Decode,
    DictMerge,
    ListUnique,
]
