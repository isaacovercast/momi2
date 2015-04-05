from __future__ import division
import pytest
from ad import gh, adnumber
from ad.admath import exp,log
import numpy as np
from size_history import ConstantTruncatedSizeHistory, PiecewiseHistory
import networkx as nx
from demography import Demography, normalizing_constant
import random
from sum_product import SumProduct

def num_grad(f,x,eps=1e-4):
    ret = []
    for i in range(len(x)):
        dx = np.zeros(len(x))
        dx[i] = eps
        ret.append((f(x+dx) - f(x)) / eps)
    return np.array(ret)

# this is numerically unstable for smaller epsilon
def num_hess(f,x,eps=1e-4):
    def g(y):
        return num_grad(f,y,eps)
    return num_grad(g,x,eps*eps)

def check_gradient(f, x):
    xd = np.asarray(adnumber(x))
    fxd = f(xd)
    grad1 = np.asarray(fxd.gradient(xd))

    grad2 = num_grad(f, x)

    print x, "\n", f(x)

    print grad1, "\n", grad2
    approx_zero = np.logical_or(np.abs(grad1) < 1e-15, np.abs(grad2) < 1e-15)
    not_zero = np.logical_not(approx_zero)
    if np.any(not_zero):
        assert max(np.abs(np.log(grad1[not_zero] / grad2[not_zero]))) < 1e-2 
    if np.any(approx_zero):
        assert np.all(grad1[approx_zero] < 1e-15) and np.all(grad2[approx_zero] < 1e-15)

    # avoid doing numerical hessian for now as it is unstable
#     hess1 = np.asarray(map(np.asarray, fxd.hessian(xd)))
#     hess2 = num_hess(f,x)
#     print hess1,"\n",hess2
#     assert np.max(np.log(hess1 / hess2)) < 1e-2

def test_simple():
    def f(x):
        return np.sum(np.outer(x,x))
    check_gradient(f, np.random.normal(size=10))

def test_simple_2():
    def f(x):
        return np.sum(1.0 / np.outer(x,x))
    check_gradient(f, np.random.normal(size=10))

def test_simple_3():
    def f(x):
        #return sum(x/x)
        return sum(x) / sum(x)
    check_gradient(f, np.random.normal(size=10))

def piecewise_constant_demo(x, n_lins):
    assert len(x) % 2 == 1
    assert n_lins.keys() == ['a']
    n = n_lins['a']

    pieces = []
    for i in range(int((len(x)-1)/2)):
        pieces.append(ConstantTruncatedSizeHistory(n, exp(x[2*i]), exp(x[2*i+1])))
    pieces.append(ConstantTruncatedSizeHistory(n, float('inf'), exp(x[-1])))
    sizes = PiecewiseHistory(pieces)

    demo = nx.DiGraph([])
    demo.add_node('a')
    nd = dict(demo.nodes(data=True))
    nd['a']['lineages'] = n_lins['a']
    demo = Demography(demo)
    nd = demo.node_data['a']
    nd['model'] = sizes

    return demo


def sfs_func(demo_func, n_lins, normalized=True):
    # get random sfs entry
    n = sum([x for _,x in n_lins.items()])
    total_der = 0
    while total_der == 0 or total_der == n:
        total_der = 0
        states = {}
        for pop,n_pop in n_lins.items():
            n_der = random.randint(0,n_pop)
            assert n_der >= 0 and n_der <= n_pop
            total_der += n_der
            states[pop] = {'ancestral' : n_pop - n_der, 'derived' : n_der}
    
    print states
    def f(x):
        demo = demo_func(x, n_lins)
        demo.update_state(states)
        #return SumProduct(demo).p(normalized=normalized)
        ret = SumProduct(demo).p(normalized=False)
        if normalized:
            ret = ret / demo.totalSfsSum
            #ret = log(ret) - log(demo.totalSfsSum)
        return ret
    return f

@pytest.mark.parametrize("n,epochs,normalized", 
                         ((2,1,norm) for norm in (False,True)))
def test_piecewise_constant_p(n, epochs, normalized):
    n_lins = {'a' : n}

    #x = np.random.normal(size=2*epochs - 1)
    x = np.zeros(2*epochs-1)
    f = sfs_func(piecewise_constant_demo, n_lins, normalized=normalized)

    check_gradient(f,x)


def normalizing_constant_func(demo_func, n_lins):
    def f(x):
        demo = demo_func(x, n_lins)
        return demo.totalSfsSum
    return f

@pytest.mark.parametrize("n,epochs", 
                         ((5,5),))
def test_piecewise_constant_normalizing(n, epochs):
    n_lins = {'a' : n}

    x = np.random.normal(size=2*epochs - 1)
    f = normalizing_constant_func(piecewise_constant_demo, n_lins)

    check_gradient(f,x)