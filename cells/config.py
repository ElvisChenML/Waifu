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
        self.data = None

    async def load_config(self, completion: bool = True):
        if not os.path.exists(self.config_file) and os.path.exists(self.template_file):
            # 如果配置文件不存在，并且提供了模板，则使用模板创建配置文件
            shutil.copyfile(self.template_file, self.config_file)

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
            with open(self.config_file, "r", encoding="utf-8") as config_file:
                config_lines = config_file.readlines()

            new_config_lines = []
            for line in config_lines:
                if ":" in line:
                    key_value_comment = line.split("#", 1)
                    key_value = key_value_comment[0].split(":", 1)
                    if len(key_value) == 2:
                        key = key_value[0].strip()
                        comment = f" #{key_value_comment[1]}" if len(key_value_comment) > 1 else ""
                        if key in self.data:
                            value = self.data[key]
                            new_config_lines.append(f"{key}: {value}{comment}\n")
                        else:
                            new_config_lines.append(line)
                    else:
                        new_config_lines.append(line)
                else:
                    new_config_lines.append(line)

            # 将新的配置写回文件
            with open(self.config_file, "w", encoding="utf-8") as config_file:
                config_file.writelines(new_config_lines)

            # 其他补充配置或校验逻辑
            # 例如：验证配置项的值是否在合理范围内，初始化某些依赖项等

    def save_config(self):
        with open(self.config_file, "r", encoding="utf-8") as config_file:
            config_lines = config_file.readlines()

        new_config_lines = []
        for line in config_lines:
            stripped_line = line.strip()
            if stripped_line:
                if ":" in stripped_line:
                    key_value_comment = stripped_line.split("#", 1)
                    key_value = key_value_comment[0].split(":", 1)
                    if len(key_value) == 2:
                        key = key_value[0].strip()
                        comment = f" #{key_value_comment[1]}" if len(key_value_comment) > 1 else ""
                        if key in self.data:
                            value = self.data[key]
                            new_config_lines.append(f"{key}: {value}{comment}")
                        else:
                            new_config_lines.append(line)
                    else:
                        new_config_lines.append(line)
                else:
                    new_config_lines.append(line)

        with open(self.config_file, "w", encoding="utf-8") as config_file:
            config_file.writelines(new_config_lines)
