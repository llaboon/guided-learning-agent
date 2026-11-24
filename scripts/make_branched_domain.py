"""Generate data/domains/early_math_branched.json from early_math.json.

Design (pre-registered in COORDINATION.md §12): keep the original 13 skills
verbatim and add 8 skills in three new parallel strands plus cross-branch
prerequisites:

  strands: 形状 (shape_basic -> shape_compose), 规律 (pattern_ab ->
  pattern_abc), 方位 (position_direction);
  cross edges: shape_count <- shape_basic + counting_objects;
               number_pattern <- pattern_ab + counting_10;
               classify_attr <- shape_basic + quantity_compare.

File order (=> KnowledgeMap topological order) is a level-wise interleave:
roots first, then level-1, then the counting-strand level-2 together with the
new cross-prereq skills, then the remaining original chain. This is a
plausible multi-strand kindergarten curriculum and -- unlike an append-only
order -- exercises the parallel strands within a 24-turn session budget.
"""
import io
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

NEW_SKILLS = [
    {
        "id": "shape_basic",
        "name": "认识基本图形",
        "description": "认识圆形、正方形、三角形、长方形，并能说出名称",
        "prerequisites": [],
        "difficulty": 1,
        "misconceptions": ["三角形和正方形混淆", "把长方形说成正方形"],
        "teach_hints": "用实物（积木、饼干、盘子）边摸边认；把形状比喻成身边的东西：太阳是圆的。",
        "items": [
            {"form": "A", "q": "这个圆圆的、没有角的图形叫什么？", "a": "圆形"},
            {"form": "A", "q": "有四条一样长的边、四个直角的图形叫什么？", "a": "正方形"},
            {"form": "B", "q": "由三条边围成的图形叫什么？", "a": "三角形"},
            {"form": "B", "q": "有两个长边、两个短边的图形叫什么？", "a": "长方形"},
        ],
        "practice": [
            {"q": "看看积木，哪一块是三角形的？指给我看。", "a": "三角形"},
        ],
    },
    {
        "id": "position_direction",
        "name": "空间方位",
        "description": "认识上下、前后、里外等基本空间方位",
        "prerequisites": [],
        "difficulty": 1,
        "misconceptions": ["上下与里外混淆", "前后颠倒"],
        "teach_hints": "用身体和实物演示：把玩具藏到盒子里面、桌子下面，让孩子找并说出位置。",
        "items": [
            {"form": "A", "q": "小球被放进盒子里面了，小球在哪里？", "a": "里面"},
            {"form": "A", "q": "小鸟在树的上方飞，是在树的上面还是下面？", "a": "上面"},
            {"form": "B", "q": "小鱼在水里游，水里是小鱼的里面还是外面？", "a": "里面"},
            {"form": "B", "q": "小猫藏在门后面，是在门的前面还是后面？", "a": "后面"},
        ],
        "practice": [
            {"q": "把你的手举到头顶上面我看看。", "a": "上面"},
        ],
    },
    {
        "id": "pattern_ab",
        "name": "AB规律",
        "description": "发现并延续简单交替规律（ABAB）",
        "prerequisites": [],
        "difficulty": 2,
        "misconceptions": ["接续时不看前文随意说", "只重复上一个元素"],
        "teach_hints": "用串珠、拍手游戏演示：红蓝红蓝、拍手跺脚拍手跺脚，让孩子接着说。",
        "items": [
            {"form": "A", "q": "红色、蓝色、红色、蓝色……接下来是什么颜色？", "a": "红色"},
            {"form": "A", "q": "苹果、香蕉、苹果、香蕉……接下来是什么？", "a": "苹果"},
            {"form": "B", "q": "圆形、三角形、圆形、三角形……接下来是什么形状？", "a": "圆形"},
            {"form": "B", "q": "拍手、跺脚、拍手、跺脚……接下来做什么？", "a": "拍手"},
        ],
        "practice": [
            {"q": "我们玩串珠子：红、蓝、红、蓝……你接着串一个什么颜色？", "a": "红色"},
        ],
    },
    {
        "id": "shape_compose",
        "name": "图形拼搭",
        "description": "用基本图形拼出组合图形，理解图形之间的关系",
        "prerequisites": ["shape_basic"],
        "difficulty": 3,
        "misconceptions": ["不理解拼合关系，仍按单个图形描述"],
        "teach_hints": "用七巧板或两个三角形纸片实际拼一拼：两个三角形拼成正方形。",
        "items": [
            {"form": "A", "q": "两个一样大的三角形拼在一起，可以拼成什么形状？", "a": "正方形"},
            {"form": "A", "q": "两个正方形并排拼在一起，会变成什么形状？", "a": "长方形"},
            {"form": "B", "q": "一个正方形从中间剪开，变成两个什么形状？", "a": "三角形"},
            {"form": "B", "q": "四个小正方形可以拼成一个大什么？", "a": "正方形"},
        ],
        "practice": [
            {"q": "用两块三角形积木，试试能不能拼出一个正方形。", "a": "正方形"},
        ],
    },
    {
        "id": "pattern_abc",
        "name": "复杂规律",
        "description": "发现并延续 AAB、ABC 等更复杂的规律",
        "prerequisites": ["pattern_ab"],
        "difficulty": 3,
        "misconceptions": ["按 ABAB 惯性接续而忽略第三个元素", "只看最后一个元素"],
        "teach_hints": "把规律念出声：红红蓝、红红蓝；帮助孩子找到重复的单元。",
        "items": [
            {"form": "A", "q": "红色、红色、蓝色、红色、红色、蓝色……接下来是什么颜色？", "a": "红色"},
            {"form": "A", "q": "大、小、中、大、小、中……接下来是什么？", "a": "大"},
            {"form": "B", "q": "苹果、苹果、梨、苹果、苹果、梨……接下来是什么？", "a": "苹果"},
            {"form": "B", "q": "三角形、圆形、圆形、三角形、圆形、圆形……接下来是什么形状？", "a": "三角形"},
        ],
        "practice": [
            {"q": "跟着我念：红红蓝、红红蓝……接下来该念什么颜色？", "a": "红色"},
        ],
    },
    {
        "id": "shape_count",
        "name": "图形计数",
        "description": "在一组图形中按类别数出数量",
        "prerequisites": ["shape_basic", "counting_objects"],
        "difficulty": 3,
        "misconceptions": ["把不同形状混在一起数", "漏数或重复数"],
        "teach_hints": "把同类图形先圈出来再数；数一个划掉一个。",
        "items": [
            {"form": "A", "q": "图里摆着2个圆形和3个三角形，三角形一共有几个？", "a": "3"},
            {"form": "A", "q": "一排图形：圆形、三角形、圆形、三角形，圆形一共有几个？", "a": "2"},
            {"form": "B", "q": "图里有4个正方形和2个三角形，正方形一共有几个？", "a": "4"},
            {"form": "B", "q": "一排图形：三角形、圆形、三角形、圆形、三角形，三角形一共有几个？", "a": "3"},
        ],
        "practice": [
            {"q": "把桌上的积木按形状分开，数数三角形的有几块？", "a": "3"},
        ],
    },
    {
        "id": "number_pattern",
        "name": "数字规律",
        "description": "发现数列的排列规律并延续",
        "prerequisites": ["pattern_ab", "counting_10"],
        "difficulty": 3,
        "misconceptions": ["乱猜下一个数", "只重复上一个数"],
        "teach_hints": "把数列念出声找规律：每次多1，或者每次多2；用积木排一排验证。",
        "items": [
            {"form": "A", "q": "1、2、3、4、接下来是几？", "a": "5"},
            {"form": "A", "q": "2、4、6、接下来是几？", "a": "8"},
            {"form": "B", "q": "5、6、7、接下来是几？", "a": "8"},
            {"form": "B", "q": "1、3、5、接下来是几？", "a": "7"},
        ],
        "practice": [
            {"q": "我们一起数：1、2、3、4……你接着说一个数？", "a": "5"},
        ],
    },
    {
        "id": "classify_attr",
        "name": "按属性分类",
        "description": "按颜色、形状、大小等属性对物体分类并说出标准",
        "prerequisites": ["shape_basic", "quantity_compare"],
        "difficulty": 3,
        "misconceptions": ["分类标准中途变化", "说不出按什么分的"],
        "teach_hints": "先给一个分好的例子问为什么这样分，再让孩子自己分并解释。",
        "items": [
            {"form": "A", "q": "红色积木3块、蓝色积木2块，按颜色分能分成几类？", "a": "2"},
            {"form": "A", "q": "把圆形和三角形分开摆放，是按形状还是按大小分的？", "a": "形状"},
            {"form": "B", "q": "大球2个、小球3个，按大小分能分成几类？", "a": "2"},
            {"form": "B", "q": "气球按红色一堆、蓝色一堆摆放，是按颜色还是按大小分的？", "a": "颜色"},
        ],
        "practice": [
            {"q": "把玩具分成两堆，告诉我你是按什么分的？", "a": "颜色"},
        ],
    },
]

# level-wise interleave (see module docstring); must be a valid topological order
FULL_ORDER = [
    "counting_10", "shape_basic", "position_direction", "pattern_ab",
    "counting_objects", "number_recognition", "shape_compose", "pattern_abc",
    "quantity_compare", "ordinal", "zero_concept",
    "shape_count", "number_pattern",
    "classify_attr", "composition_5",
    "addition_5", "subtraction_5",
    "composition_10",
    "addition_10", "subtraction_10",
    "word_problem_10",
]


def main():
    src = json.load(io.open("data/domains/early_math.json", encoding="utf-8"))
    orig = {s["id"]: s for s in src["skills"]}
    new = {s["id"]: s for s in NEW_SKILLS}
    assert not (set(orig) & set(new)), "id clash"
    merged = []
    for sid in FULL_ORDER:
        if sid in orig:
            merged.append(orig[sid])
        else:
            assert sid in new, f"unknown skill in FULL_ORDER: {sid}"
            merged.append(new[sid])
    assert len(merged) == 21, len(merged)

    # validate: prereqs appear earlier (topological)
    pos = {s["id"]: i for i, s in enumerate(merged)}
    for s in merged:
        for p in s.get("prerequisites", []):
            assert p in pos, f"{s['id']}: unknown prereq {p}"
            assert pos[p] < pos[s["id"]], f"{s['id']}: prereq {p} after it"

    out = {
        "domain_id": "early_math_branched",
        "name": "幼儿基础数学（分叉扩展版）",
        "description": "早期数学分叉域：在原 13 技能线性主链基础上增加形状/规律/方位三条平行支线"
                       "与三条跨支线先修边（图形计数、数字规律、按属性分类），共 21 技能。"
                       "用于检验自适应规划在分叉领域图上的增益（COORDINATION §12）。",
        "version": 1,
        "skills": merged,
    }
    p = "data/domains/early_math_branched.json"
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"written {p}: {len(merged)} skills")
    print("order:", " -> ".join(FULL_ORDER[:8]), "...")
    roots = [s["id"] for s in merged if not s["prerequisites"]]
    print("roots:", roots)


if __name__ == "__main__":
    main()
