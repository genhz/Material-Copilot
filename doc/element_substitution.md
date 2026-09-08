# 元素替换工具 (Element Substitution Tool)

## 功能说明

`ElementSubstitutionTool` 是一个 LangChain Tool，用于修改晶体结构中的元素组成。当你想进行以下操作时可以使用：

- **元素替代**：如 "把 Fe 替换成 Co"
- **元素掺杂**：如 "用 La 部分替代 Nd"
- **化学式修改**：如 "将 Nd2Fe14B 改为 La2Fe14B"

## 数据策略

工具采用**智能数据获取策略**：

```
1. 执行元素替换 → 生成新化学式
   │
   ▼
2. 查询 Materials Project
   │
   ├── 找到 ──▶ 使用 MP 真实物性数据（带隙、磁性、形成能等）
   │
   └── 未找到 ──▶ 使用计算值并标注
                   ├─ 几何数据：密度、空间群（从结构计算）
                   └─ 物性数据：标记为"需 DFT 计算"
```

### 返回数据中的标识

```json
{
  "formula": "Nd2Co14B",
  "material_id": "mp-123456",      // 或 "substituted"
  "data_source": "MP",             // 或 "calculated"
  "note": "元素替换后从 MP 查询到 mp-123456 的真实数据"
}
```

| data_source | 说明 | 数据可信度 |
|-------------|------|-----------|
| `MP` | 从 Materials Project 查询到真实数据 | ⭐⭐⭐⭐⭐ 实验/计算值 |
| `calculated` | 仅几何结构计算，物性数据缺失 | ⭐⭐⭐ 几何准确，物性需 DFT |

## 使用方式

### 通过自然语言调用

用户可以直接对 AI 助手说：

```
"把 Nd2Fe14B 中的 Fe 全部替换成 Co"
"用 La 替代 Nd2Fe14B 中的 Nd"
"我想看看 (Nd0.5La0.5)2Fe14B 的结构"
```

Agent 会自动：
1. 识别用户意图
2. 调用 `element_substitution` 工具
3. 返回替换后的新结构和化学式
4. 如果 MP 有数据，显示真实物性；否则标注"需 DFT 计算"

### 工具参数

```python
{
    "cif": "当前材料的 CIF 文件内容",
    "substitutions": {"Fe": "Co", "Nd": "La"},  # 替换规则
    "current_formula": "Nd2Fe14B"
}
```

## 工作原理

```
1. 从 CIF 解析晶体结构 (pymatgen Structure)
   │
   ▼
2. 遍历所有原子位点，应用替换规则
   │
   ▼
3. 生成新的 CIF 文件和化学式
   │
   ▼
4. 用新化学式查询 Materials Project
   │
   ├── 找到 ──▶ 返回 MP 真实数据 + 新 CIF
   │
   └── 未找到 ──▶ 计算几何数据 (密度、空间群)
                   │
                   ▼
                 标注 data_source="calculated"
```

## 示例代码

```python
from skills.element_substitution import ElementSubstitutionTool

tool = ElementSubstitutionTool()

# 执行替换
result_json = tool._run(
    cif=cif_content,
    substitutions={"Fe": "Co"},
    current_formula="Nd2Fe14B"
)

# 解析结果
import json
result = json.loads(result_json)
print(f"新化学式：{result['formula']}")
print(f"数据来源：{result['data_source']}")  # "MP" 或 "calculated"
print(f"备注：{result['note']}")

if result['data_source'] == "MP":
    print(f"MP 材料 ID: {result['material_id']}")
    print(f"带隙：{result['band_gap']} eV")
else:
    print("物性数据需 DFT 计算")
```

## 返回数据格式

### 情况 1: MP 有数据

```json
{
  "formula": "Nd2Co14B",
  "material_id": "mp-123456",
  "band_gap": 0.85,
  "is_magnetic": true,
  "formation_energy": -0.52,
  "cif": "...",
  "density": 8.12,
  "spacegroup_symbol": "I4_1/m",
  "spacegroup_number": 87,
  "crystal_system": "tetragonal",
  "formula_unit": 68,
  "magnetic_ordering": "FM",
  "elements": ["Nd", "Co", "B"],
  "pretty_formula": "Nd2Co14B",
  "data_source": "MP",
  "note": "元素替换后从 MP 查询到 mp-123456 的真实数据"
}
```

### 情况 2: MP 无数据

```json
{
  "formula": "Nd2Co14B",
  "material_id": "substituted",
  "band_gap": null,
  "is_magnetic": null,
  "formation_energy": null,
  "cif": "...",
  "density": 8.05,
  "spacegroup_symbol": "I4_1/m",
  "spacegroup_number": 87,
  "crystal_system": "tetragonal",
  "formula_unit": 68,
  "magnetic_ordering": null,
  "elements": ["Nd", "Co", "B"],
  "pretty_formula": "Nd2Co14B",
  "data_source": "calculated",
  "note": "替换后的材料在 Materials Project 中未找到，物性数据需 DFT 计算"
}
```

## 注意事项

### ⚠️ 重要限制

1. **晶体框架保持不变**：元素替换仅改变原子类型，不改变晶体结构框架。实际中，元素替换可能导致晶格畸变或相变。

2. **化学合理性**：工具不会验证替换的化学合理性（如离子半径匹配、电荷平衡、形成能等）。用户需要自行判断替换是否有意义。

3. **MP 数据匹配**：即使 MP 有相同化学式的材料，其晶体结构可能与替换后的结构不同（多型体、不同空间群等）。此时 MP 数据仅供参考。

### ✅ 最佳实践

- 对于**同价元素替换**（如 Fe↔Co, Nd↔La），结果通常可靠
- 对于**掺杂比例**，建议先用小比例测试
- 替换后应检查 CIF 结构是否合理（键长、配位环境等）
- 重要结论应通过 DFT 计算验证

## 依赖

- `pymatgen` - 晶体结构处理
- `mp-api` - Materials Project 查询
- `langchain_core` - Tool 接口
