项目名建议：**payLite**  
你的仓库地址：https://github.com/wangyifan349/payLite

---

# README.md

```markdown
# payLite

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**AlipayLite** 是一个基于 Flask 和 SQLite3 的简易支付宝模拟系统，实现了多用户注册、登录、余额管理、用户间转账、详细转账记录及 JSON 历史记录导出等功能，并带有美观的 Bootstrap 金色主题前端界面。本项目所有代码、安全细节与注释规范，适合 Flask 学习、教案演示或资金跟踪管理原型开发。

## 特性

- 用户注册、登录、注销，所有密码本地存储，初始余额为 0
- 查询个人余额
- 根据对方用户ID进行转账操作，安全充足校验
- 展示详细转账流水，每一笔历史交易记录均显示变动后余额
- 一键导出全部收支明细及余额变动历史为 JSON（前端和公开 API）
- API 导出接口需持有当前用户 token，保证数据私有安全
- 前端基于 Bootstrap 金色风格，体验优秀
- 代码清晰分层，所有重要 SQL 均有中文注释，无不规范代码

## 在线预览

暂无 Demo，需本地部署。界面效果如下图所示：

![AlipayLite截图](https://raw.githubusercontent.com/whatdo/AlipayLite/main/docs/screenshot.png)

## 快速开始

**环境需求：**  
- Python 3.7+
- Flask

**安装依赖：**
```bash
pip install flask
```

**启动应用：**
```bash
python app.py
```

**访问地址：**  
浏览器打开 [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

## 项目结构

```
payLite/
    app.py
    alipay.db           # 首次启动自动生成
    templates/
        base.html
        login.html
        register.html
        index.html
        transfer.html
        record.html
    static/             # (暂无静态资源)
    README.md
    LICENSE
```

## API

### 导出全量转账流水 JSON

```
GET /api/records?token=YOUR_API_TOKEN
```
返回字段包括：username, user_id, init_balance, current_balance, records(全部历史流水，含每笔后的余额快照)。

**获取方法：**  
登录后首页和转账记录页均会显示专属导出 token，可以用于 API 或前端导出。

## 开源许可

本项目遵循 [GNU General Public License v3.0](LICENSE)。

----

> 作者: [wangyifan349](https://github.com/wangyifan349)
> 欢迎 Issue、PR 讨论和学习交流！
