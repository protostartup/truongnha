from unittests import base_tests, school_unittests, mark_unittests
from unittest import TestCase, TestSuite
from app.tests import BasicWorkFlow
import inspect
import itertools

test_classes = []

def generate_test_class(module):
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, TestCase):
            if issubclass(obj, BasicWorkFlow):
                groups = obj.get_step_groups()
            else:
                groups = []
            #this character is a special char which isn't allowed to appear in method's name
            it = '*' 
            giter = groups.__iter__()
            try:
                while (True): it = itertools.product(giter.next(), it)
            except StopIteration:
                pass
            step_chain = [] #init in case of it has no element to travel
            try:
                number = 0
                while (True):
                    pr = it.next() #in the form of (a, (b, (c, ...(n, '*')...)
                    number += 1
                    step_chain = []
                    while (True):
                        step_chain.append(pr[0])
                        pr = pr[1]
                        if pr == '*': break
                    test_classes.append(
                            type(obj.__name__ + str(number),
                                (obj,), dict(step_chain=reversed(step_chain))))
            except StopIteration:
                pass

modules = [base_tests, school_unittests, mark_unittests]
for module in modules:
    generate_test_class(module)

def load_tests(loader, tests, pattern):
    suite = TestSuite()
    for test in test_classes:
        tests = loader.loadTestsFromTestCase(test)
        suite.addTests(tests)
    return suite
