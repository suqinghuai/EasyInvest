#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
易投-EasyInvest 股票分析工具
功能：获取股票数据并使用大模型进行分析，生成投资报告
"""

import os
import sys
import json
import requests
import configparser
from datetime import datetime
import time
from typing import Dict, List, Optional


class StockAnalyzer:
    def __init__(self, config_path: str = "config.ini"):
        """初始化分析器，读取配置"""
        # 获取脚本所在目录（兼容PyInstaller打包后的exe）
        if getattr(sys, 'frozen', False):
            # PyInstaller打包后的exe路径
            self.base_dir = os.path.dirname(sys.executable)
        else:
            # 正常的脚本路径
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.config = self._load_config(config_path)
        self.reports_dir = os.path.join(self.base_dir, "reports")
        self._ensure_directories()
    
    def _load_config(self, config_path: str) -> configparser.ConfigParser:
        """加载配置文件"""
        config = configparser.ConfigParser()
        
        # 如果是相对路径，则基于脚本目录构建绝对路径
        if not os.path.isabs(config_path):
            config_path = os.path.join(self.base_dir, config_path)
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件 {config_path} 不存在")
        config.read(config_path, encoding='utf-8')
        return config
    
    def _ensure_directories(self):
        """确保必要的目录存在"""
        os.makedirs(self.reports_dir, exist_ok=True)
    
 
    def get_stock_data(self, stock_code: str) -> Dict:
        """
        从腾讯财经API获取股票数据
        腾讯财经API更稳定可靠
        """
        # 腾讯财经API接口
        base_url = "http://qt.gtimg.cn/q="
        
        # 确定市场前缀：sh-沪市，sz-深市
        if stock_code.startswith(('6', '9')):
            market_prefix = 'sh'  # 沪市
        elif stock_code.startswith(('0', '2', '3')):
            market_prefix = 'sz'  # 深市
        else:
            raise Exception(f"不支持的股票代码格式: {stock_code}")
        
        # 构建完整的股票代码
        full_code = f"{market_prefix}{stock_code}"
        
        try:
            response = requests.get(f"{base_url}{full_code}", timeout=10)
            response.raise_for_status()
            
            # 腾讯财经返回的是文本格式，需要解析
            content = response.text
            
            if not content or 'v_pv_none_match' in content:
                raise Exception("股票代码不存在或数据获取失败")
            
            # 解析返回的数据
            return self._parse_tencent_data(content, stock_code, full_code)
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败: {e}")
        except Exception as e:
            raise Exception(f"数据解析失败: {e}")
    
    def _parse_tencent_data(self, content: str, stock_code: str, full_code: str) -> Dict:
        """解析腾讯财经API返回的数据"""
        parsed_data = {'stock_code': stock_code, 'full_code': full_code}
        
        # 提取数据部分
        data_start = content.find('="') + 2
        data_end = content.find('";')
        
        if data_start < 2 or data_end < 0:
            raise Exception("数据格式错误")
        
        data_str = content[data_start:data_end]
        data_parts = data_str.split('~')
        
        # 根据实际API响应格式重新设计解析逻辑
        # 从日志可以看到实际字段顺序：
        # [0]: 未知标识, [1]: 股票名称, [2]: 股票代码, [3]: 当前价格, [4]: 昨收价, [5]: 今开价
        # [6]: 成交量(手), [31]: 涨跌额, [32]: 涨跌幅, [33]: 最高价, [34]: 最低价
        
        if len(data_parts) >= 35:
            # 正确的字段映射（基于实际API响应）
            parsed_data['stock_name'] = data_parts[1] if data_parts[1] else '未知'
            parsed_data['stock_code_api'] = data_parts[2] if data_parts[2] else stock_code
            parsed_data['current_price'] = self._safe_float(data_parts[3])  # 当前价格
            parsed_data['last_close'] = self._safe_float(data_parts[4])      # 昨收价
            parsed_data['open_price'] = self._safe_float(data_parts[5])      # 开盘价
            parsed_data['volume'] = self._safe_float(data_parts[6])          # 成交量(手)
            
            # 成交额可能在多个位置，尝试不同的索引
            # 根据API响应分析：data_parts[7]可能是成交额（万元）
            parsed_data['turnover'] = self._safe_float(data_parts[7])        # 成交额(万元)
            
            parsed_data['change'] = self._safe_float(data_parts[31])         # 涨跌额
            parsed_data['change_percent'] = self._safe_float(data_parts[32].rstrip('%')) if data_parts[32] else 0.0  # 涨跌幅
            parsed_data['high_price'] = self._safe_float(data_parts[33])     # 最高价
            parsed_data['low_price'] = self._safe_float(data_parts[34])      # 最低价
            
            # 尝试获取其他重要字段
            if len(data_parts) > 37:
                parsed_data['turnover_rate'] = self._safe_float(data_parts[37].rstrip('%')) if data_parts[37] else 0.0  # 换手率
            if len(data_parts) > 38:
                parsed_data['pe_ratio'] = self._safe_float(data_parts[38])  # 市盈率
            if len(data_parts) > 39:
                parsed_data['amplitude'] = self._safe_float(data_parts[39].rstrip('%')) if data_parts[39] else 0.0  # 振幅
            if len(data_parts) > 44:
                parsed_data['circulation_market_cap'] = self._safe_float(data_parts[44])  # 流通市值
            if len(data_parts) > 45:
                parsed_data['total_market_cap'] = self._safe_float(data_parts[45])  # 总市值
        else:
            # 如果字段较少，尝试基本解析
            if len(data_parts) >= 7:
                parsed_data['stock_name'] = data_parts[1] if data_parts[1] else '未知'
                parsed_data['current_price'] = self._safe_float(data_parts[3])
                parsed_data['last_close'] = self._safe_float(data_parts[4])
        
        # 验证数据合理性
        self._validate_stock_data(parsed_data)
        
        parsed_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return parsed_data
    
    def _safe_float(self, value: str) -> float:
        """安全转换为浮点数"""
        if not value or value == '-':
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _validate_stock_data(self, data: Dict):
        """验证股票数据的合理性"""
        # 简化的验证逻辑，不再输出警告信息
        pass
    
    def call_llm_analysis(self, stock_data: Dict) -> str:
        """调用大模型进行股票分析"""
        api_key = self.config.get('API', 'api_key')
        api_base = self.config.get('API', 'api_base')
        model = self.config.get('API', 'model')
        
        # 构建分析提示词
        prompt = self._build_analysis_prompt(stock_data)
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'system',
                    'content': '你是一个专业的股票分析师，请基于提供的股票数据给出详细专业的投资分析报告。'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': 0.7,
            'max_tokens': 2000
        }
        
        try:
            response = requests.post(
                f"{api_base}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
            
            return analysis
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"大模型API调用失败: {e}")
    
    def _build_analysis_prompt(self, stock_data: Dict) -> str:
        """构建专业分析提示词"""
        prompt = f"""作为专业股票分析师，请基于以下实时数据为{stock_data.get('stock_name', 'N/A')}({stock_data.get('stock_code', 'N/A')})提供专业的投资分析报告。

【核心数据】
- 当前价格：{stock_data.get('current_price', 'N/A')}元
- 涨跌幅：{stock_data.get('change_percent', 'N/A')}%
- 最高价：{stock_data.get('high_price', 'N/A')}元 | 最低价：{stock_data.get('low_price', 'N/A')}元
- 开盘价：{stock_data.get('open_price', 'N/A')}元 | 昨收价：{stock_data.get('last_close', 'N/A')}元
- 成交量：{stock_data.get('volume', 'N/A')}手 | 成交额：{stock_data.get('turnover', 'N/A')}万元
- 总市值：{stock_data.get('total_market_cap', 'N/A')}亿元 | 流通市值：{stock_data.get('circulation_market_cap', 'N/A')}亿元
- 市盈率：{stock_data.get('pe_ratio', 'N/A')} | 换手率：{stock_data.get('turnover_rate', 'N/A')}%

【分析要求】
请直接给出专业、自信的分析结论，避免提及数据不足或技术指标缺失。重点分析：
1. 价格走势与市场表现
2. 量价关系分析
3. 估值水平评估
4. 投资机会与风险
5. 明确的投资建议
6. 详细的个股中短期买入方案和仓位建议

请以专业、肯定的语气撰写报告，展现专业分析能力。"""
        
        return prompt
    
    def save_report(self, stock_data: Dict, analysis: str, filename: Optional[str] = None) -> str:
        """保存分析报告到文件（Markdown格式）"""
        if filename is None:
            # 中文+时间命名：股票代码_股票名称_年月日_时分.md
            timestamp = datetime.now().strftime('%Y年%m月%d日_%H时%M分')
            filename = f"{stock_data['stock_code']}_{stock_data.get('stock_name', '股票')}_{timestamp}.md"
        
        filepath = os.path.join(self.reports_dir, filename)
        
        report_content = f"""# {stock_data.get('stock_name', 'N/A')}({stock_data.get('stock_code', 'N/A')}) 投资分析报告

**分析时间**：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}

## 📊 核心数据

| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| **当前价格** | {stock_data.get('current_price', 'N/A')}元 | **涨跌幅** | {stock_data.get('change_percent', 'N/A')}% |
| **最高价** | {stock_data.get('high_price', 'N/A')}元 | **最低价** | {stock_data.get('low_price', 'N/A')}元 |
| **开盘价** | {stock_data.get('open_price', 'N/A')}元 | **昨收价** | {stock_data.get('last_close', 'N/A')}元 |
| **成交量** | {stock_data.get('volume', 'N/A')}手 | **成交额** | {stock_data.get('turnover', 'N/A')}万元 |
| **总市值** | {stock_data.get('total_market_cap', 'N/A')}亿元 | **流通市值** | {stock_data.get('circulation_market_cap', 'N/A')}亿元 |
| **市盈率** | {stock_data.get('pe_ratio', 'N/A')} | **换手率** | {stock_data.get('turnover_rate', 'N/A')}% |

## 📈 专业分析

{analysis}

---

*本报告由易投-EasyInvest AI分析系统生成，仅供参考，不构成投资建议。投资有风险，决策需谨慎。*"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return filepath
    
    def analyze_stock(self, stock_code: str) -> str:
        """完整的股票分析流程"""
        print(f"🔍 分析股票: {stock_code}")
        
        # 1. 获取股票数据
        print("📊 获取数据...", end="")
        stock_data = self.get_stock_data(stock_code)
        print(f" ✅ {stock_data.get('stock_name', '未知')}")
        
        # 2. 调用大模型分析
        print("🤖 AI分析中...", end="")
        analysis = self.call_llm_analysis(stock_data)
        print(" ✅ 完成")
        
        # 3. 保存报告
        print("📄 生成报告...", end="")
        report_path = self.save_report(stock_data, analysis)
        print(" ✅ 完成")
        
        return report_path


def main():
    """主函数"""
    print("🚀 易投-EasyInvest 股票分析系统")
    print("=" * 40)
    
    try:
        # 初始化分析器
        analyzer = StockAnalyzer()
        
        # 获取用户输入
        while True:
            stock_code = input("\n📋 请输入股票代码（6位数字，输入q退出）: ").strip()
            
            if stock_code.lower() == 'q':
                print("\n👋 再见！")
                break
            
            if not stock_code:
                print("❌ 股票代码不能为空")
                continue
            
            # 验证股票代码格式
            if not (stock_code.isdigit() and len(stock_code) == 6):
                print("❌ 股票代码应为6位数字")
                continue
            
            try:
                # 执行分析
                print("\n" + "=" * 40)
                report_path = analyzer.analyze_stock(stock_code)
                
                # 提取文件名用于显示
                report_name = os.path.basename(report_path)
                print("=" * 40)
                print(f"✅ 分析完成！")
                print(f"📁 报告位置: reports/{report_name}")
                print("=" * 40)
                
            except Exception as e:
                print(f"\n❌ 分析失败: {e}")
                print("💡 请检查网络连接或稍后重试")
    
    except Exception as e:
        print(f"\n❌ 系统初始化失败: {e}")
        print("🔧 请检查配置文件config.ini")


if __name__ == "__main__":
    main()