import astnode as ast
import visitor
import astprint
from parser import calvin_parse

class Finder(object):
    """
    Perform queries on the tree
    """
    def __init__(self):
        super(Finder, self).__init__()

    @visitor.on('node')
    def visit(self, node):
        pass

    @visitor.when(ast.Node)
    def visit(self, node):
        if node.matches(self.kind, self.attributes):
            self.matches.append(node)
        if not node.is_leaf() and self.depth < self.maxdepth:
            self.depth += 1
            map(self.visit, node.children)
            self.depth -= 1

    def find_all(self, root, kind=None, attributes=None, maxdepth=1024):
        """
        Return a list of all nodes matching <kind>, at most <maxdepth> levels
        down from the starting node <node>
        """
        self.depth = 0
        self.kind = kind
        self.maxdepth = maxdepth
        self.matches = []
        self.attributes = attributes
        self.visit(root)
        return self.matches

class DeployInfo(object):
    """docstring for DeployInfo"""
    def __init__(self, deploy_info, root, issue_tracker, known_actors=None):
        super(DeployInfo, self).__init__()
        self.root = root
        self.deploy_info = deploy_info
        self.issue_tracker = issue_tracker
        self.current_target = None

    def process(self):
        self.visit(self.root)

    @visitor.on('node')
    def visit(self, node):
        pass

    @visitor.when(ast.Node)
    def visit(self, node):
        if not node.is_leaf():
            map(self.visit, node.children)

    @visitor.when(ast.RuleApply)
    def visit(self, node):
        print "RuleApply"
        for target in node.children:
            actor_name = target.ident
            self.deploy_info['requirements'].setdefault(actor_name, [])
            self.current_target = self.deploy_info['requirements'][actor_name]
            if not node.rule.is_leaf():
                print "visit rule expression", len(node.rule.children), str(node.rule.children[0])
                map(self.visit, node.rule.children)
            self.current_target = None

    @visitor.when(ast.RulePredicate)
    def visit(self, node):
        print "RulePredicate", str(node), str(self.current_target)
        if self.current_target is None:
            return
        value = {}
        # FIXME handle union group
        value['type'] = "-" if "~" in node.op.op else "+"
        value['op'] = node.predicate.ident
        value['kwargs'] = {a.ident.ident: a.arg.value for a in node.children}

        self.current_target.append(value)

class FoldInRuleExpression(object):
    """docstring for FoldInRuleExpression"""
    def __init__(self, issue_tracker):
        super(FoldInRuleExpression, self).__init__()
        self.issue_tracker = issue_tracker

    def process(self, root):
        self.root = root
        self.visit(root)

    @visitor.on('node')
    def visit(self, node):
        pass

    @visitor.when(ast.Node)
    def visit(self, node):
        if not node.is_leaf():
            map(self.visit, node.children)

    @visitor.when(ast.RuleApply)
    def visit(self, node):
        if not node.rule.is_leaf():
            map(self.visit, node.rule.children)

    @visitor.when(ast.RulePredicate)
    def visit(self, node):
        print "Fold - RulePredicate", node.predicate.ident, node.type
        if node.type != "rule":
            return
        rules = query(self.root, kind=ast.Rule, attributes={('rule', 'ident'): node.predicate.ident})
        if not rules:
            reason = "Refers to undefined rule {}".format(node.predicate.ident)
            self.issue_tracker.add_error(reason, node)
            return
        # There should only be one rule with this ident and it should only have one child
        clone = rules[0].children[0].clone()
        node.parent.replace_child(node, clone)
        del node
        # Make sure that the clone is visited
        if not clone.is_leaf():
            map(self.visit, clone.children)

class DSCodeGen(object):

    verbose = True
    verbose_nodes = False

    """
    Generate code from a deploy script file
    """
    def __init__(self, ast_root, script_name):
        super(DSCodeGen, self).__init__()
        self.root = ast_root
        # self.verify = verify
        self.deploy_info = {
            'requirements':{},
            'valid': True
        }
        print "DSCodeGen"
        self.dump_tree('ROOT')


    def dump_tree(self, heading):
        if not self.verbose:
            return
        ast.Node._verbose_desc = self.verbose_nodes
        printer = astprint.BracePrinter()
        print "========\n{}\n========".format(heading)
        printer.process(self.root)


    def fold_in_rule_expr(self, issue_tracker):
        print "fold_in_rule_expr"
        f = FoldInRuleExpression(issue_tracker)
        f.process(self.root)
        self.dump_tree('Fold In Rule Expression')

    def generate_code_from_ast(self, issue_tracker):
        print "generate_code_from_ast"
        gen_deploy_info = DeployInfo(self.deploy_info, self.root, issue_tracker)
        gen_deploy_info.process()

    def generate_code(self, issue_tracker, verify):
        self.fold_in_rule_expr(issue_tracker)
        self.generate_code_from_ast(issue_tracker)
        self.deploy_info['valid'] = (issue_tracker.error_count == 0)


def query(root, kind=None, attributes=None, maxdepth=1024):
    finder = Finder()
    finder.find_all(root, kind, attributes=attributes, maxdepth=maxdepth)
    # print
    # print "QUERY", kind.__name__, attributes, finder.matches
    return finder.matches

def _calvin_cg(source_text, app_name):
    _, ast_root, issuetracker = calvin_parse(source_text)
    cg = DSCodeGen(ast_root, app_name)
    return cg, issuetracker

def calvin_codegen(source_text, app_name, verify=True):
    """
    Generate application code from script, return deployable and issuetracker.

    Parameter app_name is required to provide a namespace for the application.
    Optional parameter verify is deprecated, defaults to True.
    """
    cg, issuetracker = _calvin_cg(source_text, app_name)
    cg.generate_code(issuetracker, verify)
    return cg.deploy_info, issuetracker


if __name__ == '__main__':
    script = 'inline'
    source_text = \
    """
    snk : io.Print()
    1 > snk.token
    """
    ai, it = calvin_codegen(source_text, script)
    if it.issue_count == 0:
        print "No issues"
        print ai
    for i in it.formatted_issues(custom_format="{type!c}: {reason} {filename}:{line}:{col}", filename=script):
        print i





