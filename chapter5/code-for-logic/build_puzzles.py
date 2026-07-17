"""
开发用脚本：定义骑士与无赖(Knights and Knaves)谜题，
用暴力枚举校验每题「解唯一」，并导出 puzzles.json。

约定：骑士(knight)永远说真话，无赖(knave)永远说假话。
在赋值 t 中，t[name]=True 表示该岛民是骑士。
一个赋值是合法解当且仅当：对每个岛民 X，t[X] == (X 所说的话在语义上为真)。
"""
import json
from itertools import product

# 每题：id, 人数, 名字列表, 自然语言陈述(给 LLM 看), 以及用于校验的谓词。
# 谓词 stmt(name) -> 函数 f(t): 返回该岛民所说内容的“语义真值”。
PUZZLES = []


def add(pid, names, statements_nl, preds):
    PUZZLES.append(dict(id=pid, names=names, statements=statements_nl, preds=preds))


# kk01: 2 人
add("kk01", ["A", "B"],
    {"A": "B 是无赖。", "B": "我们两人都不是骑士。"},
    {"A": lambda t: not t["B"],
     "B": lambda t: (not t["A"]) and (not t["B"])})

# kk02: 2 人
add("kk02", ["A", "B"],
    {"A": "我和 B 是同一类人（要么都是骑士，要么都是无赖）。",
     "B": "我和 A 是不同类人。"},
    {"A": lambda t: t["A"] == t["B"],
     "B": lambda t: t["A"] != t["B"]})

# kk03: 2 人
add("kk03", ["A", "B"],
    {"A": "我们当中至少有一个骑士。", "B": "A 是无赖。"},
    {"A": lambda t: t["A"] or t["B"],
     "B": lambda t: not t["A"]})

# kk04: 3 人
add("kk04", ["A", "B", "C"],
    {"A": "B 是无赖。", "B": "C 是无赖。", "C": "A 和 B 都是无赖。"},
    {"A": lambda t: not t["B"],
     "B": lambda t: not t["C"],
     "C": lambda t: (not t["A"]) and (not t["B"])})

# kk05: 3 人
add("kk05", ["A", "B", "C"],
    {"A": "B 是骑士。",
     "B": "C 是无赖。",
     "C": "A 和 B 是同一类人。"},
    {"A": lambda t: t["B"],
     "B": lambda t: not t["C"],
     "C": lambda t: t["A"] == t["B"]})

# kk06: 3 人
add("kk06", ["A", "B", "C"],
    {"A": "B 和 C 是同一类人。",
     "B": "A 是无赖。",
     "C": "我和 A 是同一类人。"},
    {"A": lambda t: t["B"] == t["C"],
     "B": lambda t: not t["A"],
     "C": lambda t: t["C"] == t["A"]})

# kk07: 3 人
add("kk07", ["A", "B", "C"],
    {"A": "我是无赖，或者 B 是骑士。",
     "B": "A 是骑士。",
     "C": "B 是无赖。"},
    {"A": lambda t: (not t["A"]) or t["B"],
     "B": lambda t: t["A"],
     "C": lambda t: not t["B"]})

# kk08: 4 人
add("kk08", ["A", "B", "C", "D"],
    {"A": "B 和 D 是同一类人。",
     "B": "C 是无赖。",
     "C": "D 是骑士。",
     "D": "B 和 C 是不同类人。"},
    {"A": lambda t: t["B"] == t["D"],
     "B": lambda t: not t["C"],
     "C": lambda t: t["D"],
     "D": lambda t: t["B"] != t["C"]})

# kk09: 4 人
add("kk09", ["A", "B", "C", "D"],
    {"A": "B 是骑士。",
     "B": "C 是无赖。",
     "C": "D 是骑士。",
     "D": "A 和 B 不是同一类人。"},
    {"A": lambda t: t["B"],
     "B": lambda t: not t["C"],
     "C": lambda t: t["D"],
     "D": lambda t: t["A"] != t["B"]})

# kk10: 4 人
add("kk10", ["A", "B", "C", "D"],
    {"A": "我们四人当中至少有三个无赖。",
     "B": "A 是无赖。",
     "C": "B 是骑士。",
     "D": "C 是无赖。"},
    {"A": lambda t: (4 - sum(t.values())) >= 3,
     "B": lambda t: not t["A"],
     "C": lambda t: t["B"],
     "D": lambda t: not t["C"]})

# kk11: 5 人
add("kk11", ["A", "B", "C", "D", "E"],
    {"A": "B 是骑士。",
     "B": "C 是无赖。",
     "C": "D 是骑士。",
     "D": "E 是无赖。",
     "E": "我们五人当中至少有两个骑士。"},
    {"A": lambda t: t["B"],
     "B": lambda t: not t["C"],
     "C": lambda t: t["D"],
     "D": lambda t: not t["E"],
     "E": lambda t: sum(t.values()) >= 2})

# kk12: 5 人
add("kk12", ["A", "B", "C", "D", "E"],
    {"A": "B 是骑士。",
     "B": "C 是无赖。",
     "C": "D 是无赖。",
     "D": "E 是骑士。",
     "E": "A 和 C 是同一类人。"},
    {"A": lambda t: t["B"],
     "B": lambda t: not t["C"],
     "C": lambda t: not t["D"],
     "D": lambda t: t["E"],
     "E": lambda t: t["A"] == t["C"]})


def solve(names, preds):
    sols = []
    for combo in product([False, True], repeat=len(names)):
        t = dict(zip(names, combo))
        if all(t[n] == preds[n](t) for n in names):
            sols.append(t)
    return sols


def main():
    out = []
    for p in PUZZLES:
        sols = solve(p["names"], p["preds"])
        assert len(sols) == 1, f"{p['id']} 解不唯一: {len(sols)} 个解 -> {sols}"
        sol = {n: ("knight" if v else "knave") for n, v in sols[0].items()}
        # 组装给 LLM 的自然语言题面
        lines = [f"{n}: 「{p['statements'][n]}」" for n in p["names"]]
        desc = (
            f"这座岛上有 {len(p['names'])} 位居民：{', '.join(p['names'])}。"
            "每位居民要么是永远说真话的骑士(knight)，要么是永远说假话的无赖(knave)。"
            "他们各自说了如下的话：\n" + "\n".join(lines)
        )
        out.append(dict(id=p["id"], num_people=len(p["names"]),
                        names=p["names"], statements=p["statements"],
                        description=desc, solution=sol))
        print(f"{p['id']}: OK 唯一解 = {sol}")

    with open("puzzles.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n已写出 {len(out)} 题到 puzzles.json")


if __name__ == "__main__":
    main()
