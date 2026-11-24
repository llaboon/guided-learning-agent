"""End-to-end connectivity test: tutor & student endpoints + one dialogue round."""

import sys
import time

sys.path.insert(0, __file__.rsplit("/", 2)[0])

from gla import config
from gla.llm import Endpoint, strip_think


def main():
    print(f"tutor  : {config.TUTOR_BASE_URL}")
    print(f"student: {config.STUDENT_BASE_URL}")

    t0 = time.time()
    tutor = Endpoint(config.TUTOR_BASE_URL, config.TUTOR_MODEL, tag="tutor")
    print(f"[ok] tutor model = {tutor.model} ({time.time()-t0:.1f}s)")

    t0 = time.time()
    student = Endpoint(config.STUDENT_BASE_URL, config.STUDENT_MODEL, tag="student")
    print(f"[ok] student model = {student.model} ({time.time()-t0:.1f}s)")

    t0 = time.time()
    s_msg = strip_think(student.chat(
        [{"role": "system",
          "content": "你是一个5岁的小朋友，说话简单幼稚，不太会表达。用一句话回应老师。"},
         {"role": "user", "content": "老师问你：小朋友，你知道 2 加 3 等于几吗？"}],
        temperature=0.9, max_tokens=2048))
    print(f"[student replied {time.time()-t0:.1f}s] {s_msg[:200]}")

    t0 = time.time()
    t_msg = strip_think(tutor.chat(
        [{"role": "system",
          "content": "你是一位耐心的幼儿教师，用简单语言引导孩子思考，不直接给答案。"},
         {"role": "user", "content": f"孩子刚才说：{s_msg}\n请给出你的下一句引导。"}],
        temperature=0.7, max_tokens=2048))
    print(f"[tutor replied {time.time()-t0:.1f}s] {t_msg[:200]}")

    print("ALL_ENDPOINT_TESTS_PASSED")


if __name__ == "__main__":
    main()
