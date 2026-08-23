from app.agent.router import Skill, route


def test_routes_plain_question_to_qa():
    assert route("What did Elena Verna say about activation vs acquisition?") == Skill.qa


def test_routes_ship30_request_to_ship30_essay():
    assert route("Can you turn this into a ship 30 for 30 essay?") == Skill.ship30_essay
    assert route("write me an essay about this framework") == Skill.ship30_essay


def test_routes_artifact_request_to_artifact():
    assert route("generate a markdown document summarizing this") == Skill.artifact
    assert route("can you render this as an html landing page?") == Skill.artifact


def test_artifact_takes_precedence_over_ship30_when_both_mentioned():
    # explicit HTML/artifact intent should win over a loose "essay" mention
    assert route("turn this essay into an html artifact") == Skill.artifact


def test_case_insensitive_routing():
    assert route("PLEASE WRITE ME AN ESSAY ABOUT GROWTH LOOPS") == Skill.ship30_essay
