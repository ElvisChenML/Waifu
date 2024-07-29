import yaml
import os
import shutil


class ConfigManager:
    def __init__(self, config_name, template_name, launcher_id=""):
        self.config_name = config_name
        self.config_file = f"{config_name}.yaml"
        self.config_file_id = f"{config_name}_{launcher_id}.yaml"
        self.template_file = f"{template_name}.yaml"
        self.template_data = {}
        self.launcher_id = launcher_id
        self.data = {}

    async def load_config(self, completion: bool = True):
        if not os.path.exists(self.config_file):
            if os.path.exists(self.template_file):
                # 如果配置文件不存在，并且提供了模板，则使用模板创建配置文件
                shutil.copyfile(self.template_file, self.config_file)
                print(f"配置文件 {self.config_file} 已从模板 {self.template_file} 创建")
            else:
                # 如果模板文件不存在，输出相应的日志
                print(f"模板文件 {self.template_file} 不存在，无法创建配置文件 {self.config_file}")

        with open(self.config_file, "r", encoding="utf-8") as config_file:
            self.data = yaml.safe_load(config_file)

        if self.launcher_id:
            if not os.path.exists(self.config_file_id) and os.path.exists(self.template_file):
                # 如果config_name_{launcher_id}.yaml不存在，则创建并在每行前加上#
                with open(self.template_file, "r", encoding="utf-8") as template_file:
                    lines = template_file.readlines()
                with open(self.config_file_id, "w", encoding="utf-8") as new_config_file:
                    for line in lines:
                        if line.startswith("# "):
                            new_config_file.write(f"{line}")
                        else:
                            new_config_file.write(f"# {line}")
            if os.path.exists(self.config_file_id):
                with open(self.config_file_id, "r", encoding="utf-8") as new_config_file:
                    new_data = yaml.safe_load(new_config_file)
                    if new_data:
                        self.data.update(new_data)  # 合并new_config_file的内容，覆盖原有的配置

        if completion:
            await self.complete_config()

    async def complete_config(self):
        # 检查是否有缺失的配置项，进行补全
        updated = False

        with open(self.template_file, "r", encoding="utf-8") as template_file:
            self.template_data = yaml.safe_load(template_file)

        for key, value in self.template_data.items():
            if key not in self.data:
                self.data[key] = value
                updated = True

        if updated:
            # 复制模板内容覆盖config_name.yaml
            shutil.copyfile(self.template_file, self.config_file)

            # 检查是否有缺失的配置项，进行补全
            await self.write_config(self.config_file)

            # 其他补充配置或校验逻辑
            # 例如：验证配置项的值是否在合理范围内，初始化某些依赖项等

    async def write_config(self, file_path: str, key: str = None, value: str = None) -> None:
        with open(file_path, "r", encoding="utf-8") as config_file:
            config_lines = config_file.readlines()

        new_config_lines = []
        for line in config_lines:
            if line.strip():
                line_clean = line.lstrip("#").strip()  # 去除行首的#和两端空白
                if ":" in line_clean:
                    key_value_comment = line_clean.split("#", 1)
                    key_value = key_value_comment[0].split(":", 1)
                    if len(key_value) == 2:
                        line_key = key_value[0].strip()
                        line_value = key_value[1].strip()
                        comment = f" #{key_value_comment[1]}" if len(key_value_comment) > 1 else ""
                        if key and value:  # 更新config_file_id中键值
                            if line_key == key and line_value != value:
                                new_line = f"{line_key}: {value}{comment}\n"
                                new_config_lines.append(new_line)
                            else:
                                new_config_lines.append(line)
                        elif line_key in self.data: # 非更新的保存：保留key: value后的备注
                            new_line_value = self.data[line_key]
                            new_config_lines.append(f"{line_key}: {new_line_value}{comment}\n")
                        else:
                            new_config_lines.append(line)
                    else:
                        new_config_lines.append(line)
                else:
                    new_config_lines.append(line)

        with open(file_path, "w", encoding="utf-8") as config_file:
            config_file.writelines(new_config_lines)

    async def update_config(self, key: str, value: str):
        file_path = self.config_file
        if self.launcher_id:
            file_path = self.config_file_id
        await self.write_config(file_path, key, value)
