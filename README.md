# 开口包报价精灵 V1.1

面向覆膜购物袋业务员的 Streamlit 核价与预计 Packing List 应用。应用从 Excel 动态读取袋身和 PP 织带价格，按固定工艺规则计算 EXW、FOB 宁波、箱规和总体积，并支持手机浏览器使用。

## 本地运行

推荐 Python 3.12：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

默认地址为 `http://localhost:8501`。未配置密码时，本地开发默认密码为：业务员 `quote`，管理员 `admin`。正式部署请使用环境变量或 `.streamlit/secrets.toml` 覆盖默认密码，并通过 HTTPS 对外提供服务。

普通业务员登录后可以使用核价表单和下拉选项，查看最终报价、每项成本、总成本、计算参数和预计装箱信息，并下载内部核价单及客户英文报价单，便于发现核价问题。业务员只有查看和报价权限；汇率、公司及联系人基础信息、价格库上传和备份仅管理员可以修改。V1.1.1不在网页中提供修改密码功能；业务密码和管理员密码只能由部署负责人通过云平台环境变量或服务器密钥文件修改。

## V1.1 使用流程

1. 输入袋宽、袋高、侧宽、手提长度；订单数量默认 10,000，可用加号增加至最多 10 个阶梯。
2. 选择袋身材料、GSM、手提类型和织带规格；可选填写客户信息。
3. 按需增加附加项目（PP 版、label、魔术贴等），未填写的附加项目按 0 元/个处理。
4. 点击“提交核价”后才计算。提交后形成价格库版本、汇率、规格、数量和附加项目的不可变快照。
5. 修改任意参数会使旧结果失效，需重新提交后才能下载 PDF。

结果页提供所有数量阶梯的 EXW/FOB 单价、运输方式和预计装箱数据，并可切换查看成本明细、Packing List 和计算参数。内部核价单为中文并包含成本、损耗和利润；Customer Quotation PDF 为英文，仅显示客户可见的 USD 价格、版费、供应商联系方式和预计装箱信息。两种PDF均为可直接打印的横向A4。

管理员可保存默认英文发件人信息；核价页的折叠区域允许只为当前提交临时覆盖。PP织带可选择“特殊织带（手填价格）”，按人民币元/米、两条手提和5%裁剪损耗计算，装箱重量按20克/米保守估算。

## 数据目录和价格库

运行数据默认保存在 `data/`：

- `data/price_database.xlsx`：当前有效价格库（袋身材料和 PP 织带）。
- `data/app_settings.json`：全厂汇率和英文公司名等设置。
- `data/backups/`：价格库替换前的历史备份。

可通过环境变量 `QUOTE_DATA_DIR` 将数据目录指向云服务器上的持久化磁盘。程序发布目录和数据目录应分离，重新发布容器时不要覆盖 `data/`。

管理员在“价格库”页面上传新的 Excel。系统会检查工作表、列名、空值、负数和重复查价键；校验成功后先备份旧文件，再原子替换并清除价格缓存。校验失败继续使用上一版有效价格。当前 155 克“无纺布覆膜二等材料”价格为 `1.71 元/㎡`。

## Excel 字段

“袋身材料”工作表需要：`材料分类`、`规格克重`、`每平方米单价(元)`。

“织带材料”支持旧结构（保留颜色列，程序统一采用彩色价格）和简化结构（`样式`、`宽度（公分）`、`每米克重`、`每米单价（元）`）。简化结构中每个“样式 + 宽度”只能出现一次。

## Docker 部署

```powershell
docker build -t bag-quote-v1 .
docker run -d --name bag-quote -p 8501:8501 `
  -e APP_USER_PASSWORD="业务员密码" `
  -e APP_ADMIN_PASSWORD="管理员密码" `
  -v bag-quote-data:/app/data `
  bag-quote-v1
```

生产环境应在 Streamlit 前使用 Nginx、Caddy 或云负载均衡提供 HTTPS，并持久化挂载 `/app/data`。管理员设置中的英文公司名会显示在客户 PDF 页眉，未设置时使用 `Laminated Shopping Bag Quotation`。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py quote_app tests
python -m pip check
```

测试覆盖数量阶梯约束、提交快照和附加费用、箱高与 CBM 边界、Excel 查价及备份、汇率和公司名持久化，以及内部/客户 PDF 内容隔离。
