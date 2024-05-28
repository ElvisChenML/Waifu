# Waifu

[![Github stars](https://img.shields.io/github/stars/ElvisChenML/Waifu?color=cd7373&logo=github&style=flat-square)](https://github.com/ElvisChenML/Waifu/stargazers)![github top language](https://img.shields.io/github/languages/top/ElvisChenML/Waifu?logo=github)[![License](https://img.shields.io/github/license/ElvisChenML/Waifu?&color=cd7373&style=flat-square)](./LICENSE)

<!--
## 插件开发者详阅

### 开始

此仓库是 QChatGPT 插件模板，您可以直接在 GitHub 仓库中点击右上角的 "Use this template" 以创建你的插件。  
接下来按照以下步骤修改模板代码：

#### 修改模板代码

- 修改此文档顶部插件名称信息
- 将此文档下方的`<插件发布仓库地址>`改为你的插件在 GitHub· 上的地址
- 补充下方的`使用`章节内容
- 修改`main.py`中的`@register`中的插件 名称、描述、版本、作者 等信息
- 修改`main.py`中的`MyPlugin`类名为你的插件类名
- 将插件所需依赖库写到`requirements.txt`中
- 根据[插件开发教程](https://github.com/RockChinQ/QChatGPT/wiki/7-%E6%8F%92%E4%BB%B6%E5%BC%80%E5%8F%91)编写插件代码
- 删除 README.md 中的注释内容


#### 发布插件

推荐将插件上传到 GitHub 代码仓库，以便用户通过下方方式安装。   
欢迎以 PR 或 issue 的形式投稿您的插件到[主程序文档](https://github.com/RockChinQ/QChatGPT#%E6%8F%92%E4%BB%B6%E7%94%9F%E6%80%81)

下方是给用户看的内容，按需修改
-->

## 介绍🔎

这是一个QChatGPT的插件，旨在利用程式逻辑搭配LLM创建真实感聊天机器人，探索真实的聊天体验。

* 相关Bot功能、与LLM模型交互等基础方法均由QChatGPT实现。

### 功能

✅ 画饼: 画一个不大不小的饼

⬜ 思考模块：使 AI 可以进行一定的逻辑思考，进行决策，为后续功能做铺垫。

⬜ 时间概念：模拟时间推进的状态及行为变化，并引入上下文。

⬜ 事件模块：根据状态及行为触发事件引入上下文并主动发起消息。

⬜ 情绪感知：模拟当前场景情绪，并做出相应反馈。

⬜ 记忆数据库：自动总结对话内容并导入记忆数据库，根据用户的提问引入上下文，从而实现长时记忆。

⬜ 联网搜索：根据用户的信息，自主构造搜索决策，并引入上下文。

⬜ AI 绘图支持，将绘图引入思考链，使 AI 可以生成图片，例如 AI 自拍

## 安装💻

配置完成 [QChatGPT](https://github.com/RockChinQ/QChatGPT) 主程序后使用管理员账号向机器人发送命令即可安装：

```
!plugin get https://github.com/ElvisChenML/Waifu
```
或查看详细的[插件安装说明](https://github.com/RockChinQ/QChatGPT/wiki/5-%E6%8F%92%E4%BB%B6%E4%BD%BF%E7%94%A8)

## 使用✏️

<!-- 插件开发者自行填写插件使用说明 -->

## 鸣谢🎉

感谢 [QChatGPT](https://github.com/RockChinQ/QChatGPT) 提供Bot功能及其他基础方法
感谢 [CyberWaifu](https://github.com/Syan-Lin/CyberWaifu) [koishi-plugin-oobabooga-testbot](https://github.com/HunterShenSmzh/koishi-plugin-oobabooga-testbot) 提供的思路和代码