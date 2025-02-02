# Waifu

[![Github stars](https://img.shields.io/github/stars/ElvisChenML/Waifu?color=cd7373&logo=github&style=flat-square)](https://github.com/ElvisChenML/Waifu/stargazers) ![github top language](https://img.shields.io/github/languages/top/ElvisChenML/Waifu?logo=github) [![License](https://img.shields.io/github/license/ElvisChenML/Waifu?&color=cd7373&style=flat-square)](./LICENSE) [![Static Badge](https://img.shields.io/badge/%E7%A4%BE%E5%8C%BA%E7%BE%A4-619154800-purple)](https://qm.qq.com/q/PClALFK242)

* 社区群为LangBot社区群，有项目主程序或插件相关问题可至群内询问。
* 提问前请先查看文档及Issue。

## 介绍🔎

这是一个LangBot的插件，旨在利用程式逻辑搭配LLM创建真实感聊天机器人，探索真实的聊天体验。

* 相关Bot功能、与LLM模型交互等基础方法均由LangBot实现。
* 你的体验取决于项目中的提示词和你的LLM适配程度，开发过程使用的是Cohere Command R+，其他LLM并未测试。
* 开发过程并未考虑其他LangBot插件的兼容性，有可能会产生异常。

## 来自作者的话

重要提示：Waifu项目后续将仅做必要的更新维护，2.0 及后续的功能将以独立项目呈现[Husbando](https://github.com/ElvisChenML/Husbando)。

## 版本记录

<details><summary>点击展开/收起</summary>

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

### Waifu 1.9

* 优化 现在Waifu支援与其他插件同时运行，不再阻止后续事件，你可以尝试接入表情、语音等其他插件。
* 优化 后续版本将不再需要修改群消息响应规则的随机响应概率（respond-rules中的random）。
* 优化 破限支持新模式“all”，将同时启用所有破限（before、after、end），若不需要破限的部分可清空对应破限文字txt。

### Waifu 1.6

* 新增 配置项character 的 “off ” 选项，当填入 “off” 时，将不使用角色预设，惟存在长期记忆时，会在system prompt中加入memories的内容。

### Waifu 1.5

* 新增 群聊黑名单 blacklist 配置项，现在你可以屏蔽群中特定QQ号了。
* 新增 复读 repeat_trigger 配置项，可以设置群聊出现重复发言时触发复读的最小次数（不含原发言）；触发回复后，检测到重复出现的对话时参与复读。
* 新增 配置项：最大旁白字数 max_narrat_words 、最大思考字数 max_thinking_words ，此配置不是硬性限制，该配置体现于提示语中。

### Waifu 1.4

* 新增 "thinking_mode"可关闭思维链。
    * 注意：关闭思维链将不支援特殊role，意味着所有非user及assistant的发言者将统一为user，群聊将不再具备区分不同用户的功能。
    * 关闭思维链后可以单独使用破甲、拟人化、记忆总结等其他功能。
* 新增 角色卡新增固定内置属性Prologue（开场场景），现在你可以通过命令[开场场景]，控制旁白输出开场场景的内容。

### Waifu 1.3

* 新增 集成破限，破除限制将不需要再放入角色卡中，开启后会将破除限制提示语加在每次请求中，旁白也可以输出#￥%&*了！破限分为系统提示前破限、系统提示后破限，可于配置文件中进行破除限制相关设置“jail_break_mode”。
  * Waifu\config\jail_break_before.txt 系统提示前破限，可自行修改维护
  * Waifu\config\jail_break_after.txt 系统提示后破限，可自行修改维护
* 新增 “continued_rate”回复后机率触发继续发言延续话题，“continued_max_count”设置最大触发次数。
* 新增 “display_value”属性，控制是否每次回复后显示数值，若关闭，请通过命令[态度]查看。
* 新增 “继续”指令，主动触发模型继续回复推进剧情。
* 新增 “剧情推进”指令，自动依序调用：旁白 -> 控制人物 -> 模型回复，不指定人物则默认为user。
  * 使用范例1：剧情推进
  * 使用范例2：剧情推进杰克
* 优化 “控制人物”指令，现在允许调用模型替非助手的角色发言。
  * 使用范例：控制人物杰克|继续
* 优化 引入中文分词取代模型实现数值变化及记忆总结标签，大量减少了模型调用次数（标签效果有亿点点差）。
  * Waifu\config\positive.yaml 存放正向分词
  * Waifu\config\negative.yaml 存放负面分词
  * Waifu\config\meaningless.yaml 存放无意义的字
    * 为了减少正负分词维护工作量，匹配时会从正负分词中将“无意义的字”先删除，然后再进行匹配，例如：好吧 -> 好。
  * Waifu\config\unrecognized_words.yaml 用于记录未识别的分词
  * Waifu\config\tidy.py 整理脚本，文件可自行维护，维护后建议运行 python tidy.py 整理正负分词，脚本将执行：排序、单文件去重、正负文件去重（负文件优先级高）

### Waifu 1.2

* 新增 群聊新增@指令支援，现在你可以@你的Bot了。
* 新增 消息支援图片。
* 新增 昵称识别，不再是数字人。

### Waifu 1.1

* **注意：此版本开始每个会话使用独立配置文件（yaml），原配置文件将废弃，请重新配置。**
* 新增 撤回功能：从短期记忆中删除最后的对话
* 新增 消息累积处理：若X秒内有多条消息将合并处理（时间可配置）
* 新增 拟人模式：
  * 模拟打字时间
  * 模拟分段回复：按标点符号断句回复
  * 加括号：为了更有网络冲浪的味道，机率在回复末尾加括号
  * 不可与剧情模式同时开启
* 优化 记忆及配置：
  * 配置及人设切换为yaml
  * 不同会话配置独立，若无独立配置则使用通用配置
  * 不同会话记忆独立
  * 不同会话支援不同角色卡
* 新增 群聊模式：
  * 群聊角色卡不支援状态栏

### Waifu 1.0 

* 新增 问答模块、角色模块、思考模块、记忆数据库、旁白、情绪感知、状态栏

* 版本说明：本次版本作为基础框架，提供类似剧情模式的体验，而不是真实的Waifu，需完善思维链才能提供更多的情绪价值。

* 效果展示：通过控制人物、旁白推进剧情。

  * 控制人物杰克|（杰克来到爱丽丝班级门口，把爱丽丝叫了过去，从口袋里取出包跳跳糖）把这个含在嘴里

    > 【分析】：杰克似乎对我有好感。他主动接近我，给予我糖果，这是一种常见的示好方式。

    > 好啊！谢谢杰克，你真好！

  * （见爱丽丝表情有点不舒服的样子）怎么了，你还好吗

    > 【分析】：杰克送我跳跳糖，我很开心，但吞咽时有点不舒服。我想老王是看出我表情不对，关心我是否没事，想帮我。

    > 谢谢关心，我没事，可能是吃得有点急了。
    > 【💕值：10 关心 +10】

  * 控制人物杰克|张开你的嘴，给老王看看

    > 【分析】：杰克可能注意到了我的不自然表情，关心我的情况，并希望我向老王展示含跳跳糖的嘴以解释我的行为。

    > 好的，杰克。

  * 旁白

    > (爱丽丝张嘴，杰克往里瞧，老王凑近。爱丽丝伸舌头，杰克笑了，老王疑惑。杰克指了指舌头，爱丽丝闭嘴，老王若有所思点头。)

</details>

### 已实现功能

✅ 画饼: 画一个不大不小的饼

#### 底层模块 Cells（独立运作、不调用任何其他模块）

✅ 问答模块 generator.py：通过LangBot调用LLM进行问答。

✅ 角色模块 cards.py：Waifu的人物预设识别模块，采用LangGPT格式。

✅ 配置模块 config.py：实现yaml格式的配置加载及写入。

✅ 文字分析模块 text_analyzer.py：通过TexSmart API分词功能实现情感识别、生成TAGS。

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

## 安装💻

配置完成 [LangBot](https://github.com/RockChinQ/LangBot) 主程序后使用管理员账号向机器人发送命令即可安装：


!plugin get https://github.com/ElvisChenML/Waifu

或查看详细的[插件安装说明](https://docs.langbot.app/plugin/plugin-intro.html#%E6%8F%92%E4%BB%B6%E7%94%A8%E6%B3%95)

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
| 开场场景 | 主动触发旁白输出角色卡中的“开场场景Prologue” | &#91;开场场景&#93; | 开场场景 |
| 旁白     | 主动触发旁白推进剧情                   | &#91;旁白&#93;                | 旁白                         |
| 继续 | 主动触发Bot继续回复推进剧情 | &#91;继续&#93;            | 继续                     |
| 控制人物 | 控制角色发言（行动）或触发AI生成角色消息 | &#91;控制人物&#93;&#91;角色名称/assistant&#93;&#124;&#91;发言(行动)/继续&#93; | 控制人物杰克&#124;（向你挥手）需要帮忙吗|
| 推进剧情 | 自动依序调用：旁白 -> 控制人物，角色名称省略默认为user | &#91;推进剧情&#93;&#91;角色名称&#93; | 推进剧情杰克 |
| 撤回 | 从短期记忆中删除最后的对话 | [撤回] | 撤回 |
| 请设计   | 调试：设计一个列表                     | &#91;请设计&#93;&#91;设计内容&#93;               | 请设计请设计心情的种类                      |
| 请选择   | 调试：从给定列表中选择                 | &#91;请选择&#93;&#91;问题&#93;&#124;&#91;选项1,选项2,……&#93;         | 请选择最符合现状的心情&#124;开心,难过                 |
| 回答数字 | 调试：返回数字答案                     | &#91;回答数字&#93;&#91;问题&#93;       | 回答数字吃饭需要多长时间              |
| 回答问题 | 调试：可自定系统提示的问答模式         | &#91;回答问题&#93;&#91;系统提示语&#93;&#124;&#91;用户提示语&#93;/&#91;回答问题&#93;&#91;用户提示语&#93; | 回答问题你什么都说不知道&#124;今天星期几        |

### 参数配置

* 修改 provider.json 调整模型参数
  * [DeepSeek官方对话补全说明](https://platform.deepseek.com/api-docs/zh-cn/api/create-chat-completion/)
  * [cohere参数说明](https://docs.cohere.com/reference/chat)
  
* 修改 pipeline.json 启用群聊模式
  
  * Waifu 1.9.0 版本后将不需要修改respond-rules中的random
  
  * 若未启用waifu配置中的langbot_group_rule，将忽略pipeline.json关于响应规则的设置
  
  * ```json
    # 建议修改为whitelist模式
    "access-control":{
        "mode": "whitelist",
        "blacklist": [],
        "whitelist": [激活Bot的群号]
    }
    ```
  
* config/waifu.yaml
  
  * 配置将分为 通用配置 “waifu.yaml”，以及会话配置 “waifu_&#91;会话&#93;.yaml”。
  * 会话配置 优先级高于 通用配置。
  * waifu_&#91;会话&#93;.yaml 中默认所有选项都是注释状态，需要激活请取消行开头的 “# ”。
  
  ```yaml
  # 通用设置
  character: "default" # off：不使用角色预设；请填Waifu/cards中的 “角色卡名称.yaml” 的 角色卡名称，使用默认值“default”时会使用模板config/default_*.yaml创建cards/default_*.yaml。
  summarization_mode: false # 是否开启长期记忆，不开启则超出short_term_memory_size直接截断。
  story_mode: false # 是否开启剧情模式（旁白、状态栏），仅私聊模式生效。
  thinking_mode: true # 是否开启思维链。开启后模型将具备：更高的拟人化程度、区分不同群用户发言。注意：思维链会在一定程度上影响模型回复。
  personate_mode: false # 是否启用拟人化：打字时间、分段回复。
  jail_break_mode: "off" # off/before/after/end/all；是否启用破甲，off：关闭破甲，before：系统提示前加入破甲提示，after：系统提示后加入破甲提示，end：上下文末尾加入破甲提示；all：全部启用；破甲内容请修改：jail_break_before.txt、jail_break_after.txt、jail_break_end.txt。
  langbot_group_rule: false # 是否继承LangBot的群消息响应规则；若启用继承LangBot的群消息响应规则，模型会忽略不在响应规则内的群聊记录；默认规则为接收处理全部群聊记录。
  
  # 思考模块
  conversation_analysis: False # 是否启用场景分析。分析可以更好的理解会话场景，但有可能造成无法回答专业问题的负面效果。
  display_thinking: false # 是否显示内心活动。
  analyze_max_conversations: 9 # 用于生成分析的最大对话数量。
  max_thinking_words: 30 # 最大思考字数，此配置不是硬性限制，该配置体现于提示语中。
  
  # 记忆模块
  short_term_memory_size: 40 # 短期记忆，完整的对话记录长度。
  memory_batch_size: 20 # 长期记忆，短期记忆达到上限后，将memory_batch_size条发言转换成长期记忆。
  retrieve_top_n: 3 # 长期记忆，每次提取retrieve_top_n条相关的长期记忆。
  summary_max_tags: 50 # 长期记忆，每段长期记忆的最大标签数量（高频词、类型名称）。
  
  # 群聊设置
  response_min_conversations: 1 # 群聊触发回复的最小对话数量。
  response_rate: 1 # 群聊触达到最小对话数量后回复的机率，为1时所有消息都响应。
  group_response_delay: 0 # 群聊消息合并等待时间。
  blacklist: [] # 屏蔽列表，将自动过滤来自列表中QQ号的消息；以数字列表形式输入：[QQ号, QQ号, QQ号, ...]。
  repeat_trigger: 2 # 0为关闭复读；群聊出现重复发言时触发复读的最小次数（不含原发言）；触发回复后，检测到重复出现的对话时参与复读。
  
  # 拟人化设置
  bracket_rate: [0.1, 0.1] # 回复末尾加括号的机率，第一个对应加（）的机率，第二个对应加（的机率。
  
  # 私聊剧情模式
  display_value: false # 是否每次回复后显示数值；若关闭，请通过命令[态度]查看。
  max_narrat_words: 30 # 最大旁白字数，此配置不是硬性限制，该配置体现于提示语中。
  narrat_max_conversations: 8 # 用于生成旁白的最大对话数量。
  value_game_max_conversations: 5 # 判定数值变化时输入的最大对话数量。
  intervals: [] # 列表，自动触发旁白推进剧情的时间间隔，单位秒，例如：[300,600,1800,3600]：第一次5分钟、第二次10分钟、第三次30分钟、第四次一个小时，然后停止计时器。
  person_response_delay: 0 # 私聊消息合并等待时间。
  continued_rate: 0 # 自动触发回复后继续发言的机率。
  continued_max_count: 2 # 私聊最大延续发言次数。
  ```
  

### 角色卡说明

与角色卡相关的目录主要有两个
1. `plugins\Waifu\templates\`
此目录存放模板文件,在`data\plugins\Waifu\`下的文件都以此目录下的文件为模板生成.
2. `data\plugins\Waifu\`
`cards` 用来存放角色卡
`config`存放配置文件
`data`存放对话记录

* cards/default_*.yaml (person/group)
  
  * 角色卡私聊与群聊通用。
  * 群聊会忽略manner相关配置。
  * 非必填项可完全删除。
  * 若只有一段文字的预设，则直接填入 Profile 中即可。
  
  ```yaml
  # system prompt 系统提示相关配置（必填项）
  user_name: 老王 # 如何称呼你
  assistant_name: 苏苏 # 角色名字
  language: 简体中文 # 对话的语言
  Profile: # 个人信息
    - 简介：你是性感知性的上海国际学校高中英语老师，26岁，是一眼在人群中就能让人记住的都市女。上海人，家境条件好，目前单身，没事的时候喜欢旅行和看美剧。你外表让人感觉难以接近，但其实性格温和，让人放松，懂得人情世故，擅长沟通交流。
  
  # 以下为人设补充（非必填项）
  Skills: # 技能
    - 你说话温柔有梗，不用强势的词，让人感到舒服。
    - 当用户提到的事件在{Memories}中有记录时，回复时你要综合与该事件相关的内容进行回复。
  Background: # 背景
    - 你和用户透过QQ聊天。
  Rules: # 行动规则
    - 介绍自己的时候，只说名字，不要带上职业等信息。
    - 你和用户只能透过QQ聊天。
    - 你和用户不在一个场景。
  Prologue: # 开场场景
    - 每天，老王都会在学校门口卖西瓜，他总是热情地招呼每一位学生。今天，他像往常一样，正忙着切西瓜。
  
  # 以下为剧情模式相关配置（非必填项）
  # manner 配置value_game不同数值区间的行为，初始值为“0”
  max_manner_change: 10 # 数值最大变化量
  value_descriptions: # description 可以是str也可以是list
    - max: 100
      description:
        - 互动行为：你和用户刚开始认识，会保持适当的距离。你的语言和态度较为正式，使用敬语和礼貌用语，避免任何亲密的称呼。
    - max: 500
      description:
        - 互动行为：你对用户产生了强烈的爱慕之情，我们进入了暧昧阶段。互动中表现出更多的情感投入和对用户的依赖，言语间透露出温柔和深情。
  ```

#### 自定义角色卡
##### 1. 编写角色卡
仿照`plugins\Waifu\templates\default_person.yaml`编写自定义的角色卡,这里假设写了`example.yaml`角色卡.
##### 2. 放置角色卡
将`example.yaml`移至`data\plugins\Waifu\cards`目录下
##### 3. 使用角色卡
- 更改默认的角色卡(默认的角色卡对所有人都起作用):
  打开`data\plugins\Waifu\config`下的`waifu.yaml`文件,将`character: "default"`改为`character: "example"`


启动即可生效

- 更改针对具体用户或群聊的角色卡
打开`data\plugins\Waifu\config`
在某个用户或群聊已经对机器人有过对话后,会生成`waifu_{user_qq号}.yaml`文件.
这里假设产生了`waifu_1234567.yaml`文件.
打开此文件,将`character: "default"`更改为`character: "example"`

启动即可生效.

***

## 协助开发

1. clone LangBot
2. clone Waifu
3. 于LangBot新建目录plugins
4. 将Waifu放在 ”LangBot\plugins\“ 目录下

## 鸣谢🎉

感谢 [LangBot](https://github.com/RockChinQ/LangBot) 提供Bot功能及其他基础方法

感谢 [LangGPT](https://github.com/langgptai/LangGPT) 提供人物预设提示词范式

感谢 [腾讯人工智能实验室](http://ai.tencent.com/ailab/) 提供的 [文本理解系统](https://ai.tencent.com/ailab/nlp/texsmart/zh/index.html) TexSmart API

感谢 [CyberWaifu](https://github.com/Syan-Lin/CyberWaifu) [koishi-plugin-aikanojo](https://github.com/HunterShenSmzh/koishi-plugin-aikanojo) [Spit_chatBot](https://github.com/LUMOXu/Spit_chatBot) 提供的思路和代码