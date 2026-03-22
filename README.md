# MyVeighNa 量化交易项目

## 项目结构

```
myvnpy/
├── strategies/              # 策略文件夹
│   ├── __init__.py
│   ├── double_ma_strategy.py    # 双均线策略示例
│   └── bollinger_strategy.py    # 布林带策略示例
├── run.py                   # 启动脚本
├── pyproject.toml           # 依赖包配置文件（现代方法）
└── README.md               # 项目说明
```

## 启动方法

### 1. 进入项目目录

```bash
cd /path/to/myvnpy
```

### 2. 创建并激活虚拟环境

```bash
# 创建虚拟环境（使用Python 3.13）
python3.13 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

### 3. 安装依赖包

```bash
# 使用现代方法从pyproject.toml安装依赖
pip install .

# 或者直接安装所需依赖
pip install vnpy vnpy_ctastrategy vnpy_sqlite vnpy_mysql vnpy_ctabacktester pandas==2.3.3
```

### 4. 启动 VeighNa Trader

```bash
python run.py
```

## 添加自定义策略

1. 在 `strategies/` 目录下创建新的 Python 文件，例如 `my_strategy.py`
2. 继承 `CtaTemplate` 类实现策略逻辑
3. 重启 VeighNa Trader，策略会自动加载到界面中

### 策略模板

```python
from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class MyStrategy(CtaTemplate):
    """我的策略"""
    
    author = "你的名字"
    
    # 策略参数（UI可调）
    param1: int = 10
    
    parameters = ["param1"]
    
    # 策略变量（UI显示）
    var1: float = 0
    
    variables = ["var1"]
    
    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")
        self.load_bar(10)
    
    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")
    
    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")
    
    def on_tick(self, tick: TickData):
        """Tick数据回调"""
        pass
    
    def on_bar(self, bar: BarData):
        """K线数据回调"""
        self.cancel_all()
        # 实现交易逻辑
    
    def on_trade(self, trade: TradeData):
        """成交回调"""
        pass
```

## 注意事项

- 策略类名使用驼峰命名（如 `MyStrategy`）
- 策略文件名使用下划线命名（如 `my_strategy.py`）
- UI 中显示的是策略类名，不是文件名
- 修改策略代码后需要重启 VeighNa Trader 才能生效
- **重要**：为了确保策略能够正确加载，请在项目目录下创建 `.vntrader` 文件夹，命令如下：
  ```bash
  mkdir -p .vntrader
  ```
  这将确保 VeighNa Trader 使用当前项目目录作为运行目录，从而能够正确找到 `strategies` 文件夹中的自定义策略。

## 内置技术指标

通过 `ArrayManager` 可以使用以下指标：

- `am.sma(n)` - 简单移动平均线
- `am.ema(n)` - 指数移动平均线
- `am.boll(n, dev)` - 布林带
- `am.kdj()` - KDJ指标
- `am.macd()` - MACD指标
- `am.rsi(n)` - RSI指标
- `am.atr(n)` - ATR指标
- 更多指标请参考 vnpy 文档
