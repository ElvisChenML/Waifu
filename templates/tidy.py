# 如果你手动维护了 sentiment 相关文件
# 可以执行命令 python tidy.py 会按照软件逻辑整文件
# 包括：排序、单文件去重、正负文件去重（负文件优先级高）

import yaml
import os
from typing import List


def load_yaml_dict(file: str) -> dict:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, file)
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    key = os.path.splitext(file)[0]
    if key in data:
        print(f"'{key}':{len(data[key])}")
    else:
        print(f"Key '{key}' not found in the loaded dictionary.")
    return data


def save_yaml_dict(file: str, data: dict):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file = os.path.join(script_dir, file)
    with open(file, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)


def remove_meaningless_words(text_list: List[str], meaningless: List[str]) -> List[str]:
    lst = []
    for text in text_list:
        for word in meaningless:
            text = text.replace(word, "")
        lst.append(text)
    lst = sorted(set(lst))
    return lst


print("Before:")
meaningless = load_yaml_dict("meaningless.yaml")["meaningless"]
meaningless = sorted(set(meaningless))
meaningless_dict = {"meaningless": meaningless}

positive_dict = load_yaml_dict("positive.yaml")
negative_dict = load_yaml_dict("negative.yaml")

cleaned_positive_dict = {k: remove_meaningless_words(v, meaningless) for k, v in positive_dict.items()}
cleaned_negative_dict = {k: remove_meaningless_words(v, meaningless) for k, v in negative_dict.items()}

final_positive_dict = {}
for key, value in cleaned_positive_dict.items():
    if key in cleaned_negative_dict:
        del cleaned_negative_dict[key]
    else:
        final_positive_dict[key] = value

save_yaml_dict("meaningless.yaml", meaningless_dict)
save_yaml_dict("positive.yaml", final_positive_dict)
save_yaml_dict("negative.yaml", cleaned_negative_dict)

print("After:")
load_yaml_dict("meaningless.yaml")
load_yaml_dict("positive.yaml")
load_yaml_dict("negative.yaml")
