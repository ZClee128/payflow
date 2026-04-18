# PayFlow MVP

私域自动收款 + 自动发货系统。

## 如何运行

### 1. 启动后端 (Mac 终端)

```bash
cd /Users/lizhicong/Desktop/PayFlow/backend

# 安装依赖 (如果还没安装)
pip3 install fastapi uvicorn sqlalchemy python-multipart

# 启动服务
python3 main.py
```

后端运行在: `http://localhost:8000`

### 2. 访问页面

- **商家后台**: `frontend/admin.html` (在浏览器直接打开)
  - 先去后台创建一个商品，上传你的收款码。
- **买家页面**: `frontend/index.html` (在浏览器直接打开)
  - 体验下单 -> 模拟支付 -> 获取内容。

## 核心流程

1. **商家端**: 创建商品，设定价格和发货内容，上传收款码。
2. **买家端**: 点击“立即获取”，系统分配一个带有微小偏移量的金额（例如 9.91）。
3. **支付**: 买家扫码支付。
4. **发货**: 买家点击“我已支付”，验证通过后即刻展示发货内容。

## 待办清单 (Phase 2)

- [ ] 接入真实的支付宝账单监听 API 或 浏览器扩展。
- [ ] 增加 JWT 用户认证系统。
- [ ] 移动端适配优化。
