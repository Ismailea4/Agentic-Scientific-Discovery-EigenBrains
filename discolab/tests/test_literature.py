from discolab.literature import TITLE_MATCH_MIN, title_similarity


def test_title_similarity_accepts_the_same_title_and_rejects_another_paper():
    t = "An adaptive genetic algorithm based on information entropy"
    assert title_similarity(t, t.upper() + ".") == 1.0
    assert title_similarity(t, "Deep learning for early warning signals of tipping points") < TITLE_MATCH_MIN
