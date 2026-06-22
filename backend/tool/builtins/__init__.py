from tool.builtins.get_strategy import get_strategy
from tool.builtins.read_resume import read_resume
from tool.builtins.read_skill import read_skill
from tool.builtins.save_real_question import save_real_question
from tool.builtins.search_web import search_web
from tool.builtins.trigger_scoring import trigger_scoring

TOOLS = [
    read_resume,
    read_skill,
    save_real_question,
    search_web,
    trigger_scoring,
    get_strategy,
]
