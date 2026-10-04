from discolab.literature import TITLE_MATCH_MIN, title_similarity


def test_title_similarity_accepts_the_same_title_and_rejects_another_paper():
    t = "An adaptive genetic algorithm based on information entropy"
    assert title_similarity(t, t.upper() + ".") == 1.0
    assert title_similarity(t, "Deep learning for early warning signals of tipping points") < TITLE_MATCH_MIN


def test_arxiv_feed_parsing_and_id_validation():
    from discolab.literature import is_arxiv_id, parse_arxiv_feed
    feed = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1203.4567v2</id>
    <published>2012-03-20T00:00:00Z</published>
    <title>Entropy and premature
      convergence in genetic algorithms</title>
    <summary>We study population entropy.</summary>
    <author><name>A. Author</name></author>
  </entry>
</feed>"""
    (w,) = parse_arxiv_feed(feed)
    assert w["arxiv_id"] == "1203.4567" and w["year"] == 2012
    assert w["title"] == "Entropy and premature convergence in genetic algorithms"
    assert is_arxiv_id("arXiv:1203.4567v2") and is_arxiv_id("cs/0112017") and not is_arxiv_id("W2350741577")


def test_credibility_labels_are_deterministic_and_conservative():
    from discolab.literature import credibility
    assert credibility("article", "journal", 4959, False)["label"] == "peer-reviewed · highly cited (4959)"
    assert credibility("article", "journal", 3, False)["uptake"] == "low-citation"
    assert credibility("report", None, 395, False)["status"] == "report (not peer-reviewed)"
    assert credibility("preprint", "repository", None, False, source="arxiv")["status"].startswith("preprint")
    assert credibility("article", None, 50, False)["status"] == "venue unverified"
    assert credibility("article", "journal", 900, True)["status"] == "retracted"
