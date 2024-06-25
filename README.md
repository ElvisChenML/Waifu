# Waifu

[![Github stars](https://img.shields.io/github/stars/ElvisChenML/Waifu?color=cd7373&logo=github&style=flat-square)](https://github.com/ElvisChenML/Waifu/stargazers)![github top language](https://img.shields.io/github/languages/top/ElvisChenML/Waifu?logo=github)[![License](https://img.shields.io/github/license/ElvisChenML/Waifu?&color=cd7373&style=flat-square)](./LICENSE)

## 介绍🔎

这是一个QChatGPT的插件，旨在利用程式逻辑搭配LLM创建真实感聊天机器人，探索真实的聊天体验。

* 相关Bot功能、与LLM模型交互等基础方法均由QChatGPT实现。
* 你的体验取决于项目中的提示词和你的LLM适配程度，开发过程使用的是Cohere Command R+，其他LLM并未测试。
* 开发过程并未考虑其他QChatGPT插件的兼容性，有可能会产生异常。

## 版本记录

### Waifu 2.0 预告

* 用户画像
  * 分析用户画像，进行针对性的回复。若已存在画像，则旧画像搭配新聊天记录重新输出用户画像。
    * 个性特征：分析用户的个性特征（如外向、内向、开放性等），调整AI的互动风格和语气，使之更符合用户的个性。
    * 对话内容分析：重大生活事件、工作进展、家庭情况，AI可以动态调整对话内容。
    * 提取兴趣点和爱好，如运动、音乐、电影等。积累兴趣标签，可以使AI在未来的对话中更有针对性地引导话题。另外基于用户的兴趣和偏好，推荐相关的话题和活动，增强互动的多样性和吸引力。
    * 话题评分：分析用户对不同话题的反应强度和参与度（如回复速度、回复长度、情感词汇使用等）从中推断用户的满意度和体验质量，识别用户更感兴趣的内容，并优先讨论这些内容。

* 情绪感知
  * 情感识别：分析用户的情感状态（如高兴、悲伤、愤怒等）。令AI调整其回应的语气和内容，使对话更加符合用户当前的情感状态。
  * 情感表达：通过语言表达安慰、同情、喜悦等情感。
* 事件：虚构生活细节和日常活动，加入话题中。

### Waifu 2.0 Developed

* 新增 撤回功能：从短期记忆中删除最后的对话

### Waifu 1.0 

* 新增 问答模块、角色模块、思考模块、记忆数据库、旁白、情绪感知、状态栏
* 版本说明：本次版本作为基础框架，提供类似剧情模式的体验，而不是真实的Waifu，需完善思维链才能提供更多的情绪价值。

### 已实现功能

✅ 画饼: 画一个不大不小的饼

#### 底层模块 Cells（独立运作、不调用任何其他模块）

✅ 问答模块 generator.py：通过QChatGPT调用LLM进行问答。

✅ 角色模块 cards.py：Waifu的人物预设识别模块，采用LangGPT格式。

#### 基础模块 Organs

✅ 思考模块 thoughts.py：使Bot通过预定义的思考链进行思考决策。

✅ 记忆数据库 memories.py：自动总结对话内容并导入记忆数据库，根据用户的提问引入上下文，从而实现长时记忆。

#### 功能实现 Systems

✅ 旁白 narrator.py：根据上下文推进角色状态改变。

✅ 状态栏 value_game.py：给与角色一个状态数值，不同数值可影响角色表现。

#### 辅助文件 Water

✅ 配置文件模板 templates：若无配置文件，将由模板生成。

✅ 配置文件 config：由模板生成的配置文件。

✅ 配置文件 cards：Waifu人物预设资料夹，请根据示例default.json修改创建。

✅ 过程文件 data：AI运行时产出的文件，包含记忆、人物相关生成物等，调用“删除记忆”指令时会被清空。

### 待实现功能（画饼）

⬜ 情绪感知 emotions.py：模拟当前场景情绪，并做出相应反馈。

⬜ 事件 events.py：根据状态及行为触发事件引入上下文并主动发起消息。

⬜ 联网搜索 searching.py：根据用户的信息，自主构造搜索决策，并引入上下文。

⬜ AI 绘图支持 portrait.py：将绘图引入思考链，使 AI 可以生成图片，例如 AI 自拍。

⬜ 剧情模式：控制AI以其他身份进行回复

⬜ 分身术：分离不同用户、不同人设的记忆。

## 安装💻

配置完成 [QChatGPT](https://github.com/RockChinQ/QChatGPT) 主程序后使用管理员账号向机器人发送命令即可安装：


!plugin get https://github.com/ElvisChenML/Waifu

或查看详细的[插件安装说明](https://github.com/RockChinQ/QChatGPT/wiki/5-%E6%8F%92%E4%BB%B6%E4%BD%BF%E7%94%A8)

## 使用✏️

### 命令列表

| Command  | Description                            | Usage                 | Usage Example                  |
| -------- | -------------------------------------- | --------------------- | ------------------------------ |
| 列出命令 | 列出目前支援所有命令及介绍             | &#91;列出命令&#93;            | 列出命令                     |
| 全部记忆 | 显示目前所有长短期记忆                 | &#91;全部记忆&#93;            | 全部记忆                     |
| 删除记忆 | 删除所有长短期记忆                     | &#91;删除记忆&#93;            | 删除记忆                     |
| 修改数值 | 修改Value Game的数字                   | &#91;修改数值&#93;&#91;数值&#93;         | 修改数值100              |
| 态度     | 显示当前Value Game所对应的“态度Manner” | &#91;态度&#93;                | 态度                         |
| 加载配置 | 重新加载所有配置文件（仅Waifu）        | &#91;加载配置&#93;            | 加载配置                     |
| 停止活动 | 停止旁白计时器                         | &#91;停止活动&#93;            | 停止活动                     |
| 旁白     | 主动触发旁白推进剧情                   | &#91;旁白&#93;                | 旁白                         |
| 时间表   | 列出模型生成的Waifu时间表              | &#91;时间表&#93;              | 时间表                       |
| 控制人物 | 控制角色行动或发言                     | &#91;控制人物&#93;&#91;角色名称/assistant&#93;&#124;&#91;发言/(行动)&#93;   | 控制人物杰克&#124;（向你挥手）需要帮忙吗|
| 撤回 | 从短期记忆中删除最后的对话 | [撤回] | 撤回 |
| 请设计   | 调试：设计一个列表                     | &#91;请设计&#93;&#91;设计内容&#93;               | 请设计请设计心情的种类                      |
| 请选择   | 调试：从给定列表中选择                 | &#91;请选择&#93;&#91;问题&#93;&#124;&#91;选项1,选项2,……&#93;         | 请选择最符合现状的心情&#124;开心,难过                 |
| 回答数字 | 调试：返回数字答案                     | &#91;回答数字&#93;&#91;问题&#93;       | 回答数字吃饭需要多长时间              |
| 回答问题 | 调试：可自定系统提示的问答模式         | &#91;回答问题&#93;&#91;系统提示语&#93;&#124;&#91;用户提示语&#93;/&#91;回答问题&#93;&#91;用户提示语&#93; | 回答问题你什么都说不知道&#124;今天星期几        |

### 参数配置

* 修改 provider.json 调整模型参数
  * [DeepSeek官方对话补全说明](https://platform.deepseek.com/api-docs/zh-cn/api/create-chat-completion/)
  * [cohere参数说明](https://docs.cohere.com/reference/chat)
  
* water/config/waifu.json
  * character：使用water/cards中的预设名称，使用默认值“default”时会使用模板Water/config/default_card.json创建water/cards/default.json。
  * intervals：列表，自动触发旁白推进剧情的时间间隔，单位秒，默认为[300,600,1800,3600]，即：第一次5分钟、第二次10分钟、第三次30分钟、第四次一个小时，然后停止计时器。  
  * narrat_max_conversations：用于生成旁白的最大对话数量。
  * analyze_max_conversations：用于生成分析的最大对话数量。
  * value_game_conversations：判定数值变化时输入的最大对话数量。
  * short_term_memory_size：短期记忆，完整的对话记录长度。
  * memory_batch_size：短期记忆达到上限后，将memory_batch_size条发言转换成长期记忆。
  * retrieve_top_n：每次提取retrieve_top_n条相关的长期记忆。
  * summary_min_tags：每段长期记忆的最小标签数量（不稳定）。
  
* water/cards/default.json
  * system_prompt：系统提示相关配置
    * user_name：必填项，Waifu如何称呼你
    * assistant_name：必填项，Waifu的名字
    * language：必填项，Waifu使用的语言
    * Profile：必填项，Waifu介绍
    * Skills：非必填项，Waifu的技能
    * Background：必填项，Waifu的背景
    * Rules：必填项，Waifu应遵循的规则
  * manner：配置value_game不同数值区间的行为
  * actions_type：配置value_game判定数值变化的条件

## 协助开发

1. clone QChatGPT
2. clone Waifu
3. 于QChatGPT新建目录plugins
4. 将Waifu放在 ”QChatGPT\plugins\“ 目录下

## 已知问题

* 所有角色卡共用记忆
* 所有用户共用记忆
* 不支援群聊模式

## 鸣谢🎉

感谢 [QChatGPT](https://github.com/RockChinQ/QChatGPT) 提供Bot功能及其他基础方法

感谢 [LangGPT](https://github.com/langgptai/LangGPT) 提供人物预设提示词范式

感谢 [CyberWaifu](https://github.com/Syan-Lin/CyberWaifu) [koishi-plugin-aikanojo](https://github.com/HunterShenSmzh/koishi-plugin-aikanojo) 提供的思路和代码