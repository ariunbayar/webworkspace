from pyparsing import Word, Keyword, Optional
from pyparsing import alphas, nums, alphanums
from pyparsing import ParseException


# character groups
nums
alphas
alphanums
alphas_underscore = alphas + '_'
alphanums_underscore = alphanums + '_'

# keywords
kw_var = Optional(Keyword('var'))

# parsing rules
integer = Word(nums)
variable = Word(alphas_underscore, alphanums_underscore)
variable_declare = kw_var + variable('var') + '=' + integer('value') + ';'


rules = [
    variable_declare,
    variable,
    integer,
]


def parse(snippet):
    global rules

    for rule in rules:
        try:
            parse_result = rule.parseString(snippet)
        except ParseException:
            print 'Fail: ' + repr(rule)
            continue

        return parse_result.asDict()

    return None
