
import autograd.numpy as np
from autograd.core import primitive
import scipy
from .util import memoize, check_psd
from .convolution import sum_trailing_antidiagonals, add_trailing_axis, convolve_trailing_axes, transposed_convolve_trailing_axes, roll_trailing_axes, unroll_trailing_axes
from .einsum2 import einsum1, einsum2


def par_einsum(*args):
    return einsum2(*args)

convolve_trailing_axes = primitive(convolve_trailing_axes)
transposed_convolve_trailing_axes = primitive(
    transposed_convolve_trailing_axes)

convolve_trailing_axes.defgrad(
    lambda ans, A, B: lambda g: transposed_convolve_trailing_axes(g, B, A.shape))
convolve_trailing_axes.defgrad(lambda ans, A, B: lambda g: transposed_convolve_trailing_axes(
    np.transpose(g, (0, 2, 1, 3)), A, B.shape), argnum=1)
transposed_convolve_trailing_axes.defgrad(
    lambda ans, C, B, Ashape: lambda g: convolve_trailing_axes(g, B))
transposed_convolve_trailing_axes.defgrad(lambda ans, C, B, Ashape: lambda g: transposed_convolve_trailing_axes(
    np.transpose(C, (0, 2, 1, 3)), g, B.shape), argnum=1)


def convolve_axes(arr0, arr1, labs, axes, out_axis):
    old_labs = [list(l) for l in labs]
    labs = [[l_i for l_i in l if l_i != a] + [a] for l, a in zip(labs, axes)]

    arr0, arr1 = [einsum1(a, ol, l)
                  for a, ol, l in zip((arr0, arr1), old_labs, labs)]
    reshaped_arrs = [np.reshape(
        a, (a.shape[0], -1, a.shape[-1]), order='C') for a in (arr0, arr1)]
    ret = convolve_trailing_axes(*reshaped_arrs)
    return np.reshape(ret, tuple([ret.shape[0]] + list(arr0.shape[1:-1]) + list(arr1.shape[1:-1]) + [-1]),
                      order='C'), [labs[0][0]] + labs[0][1:-1] + labs[1][1:-1] + [out_axis]

sum_trailing_antidiagonals = primitive(sum_trailing_antidiagonals)
add_trailing_axis = primitive(add_trailing_axis)

sum_trailing_antidiagonals.defgrad(
    lambda ans, A: lambda g: add_trailing_axis(g, A.shape[2]))
add_trailing_axis.defgrad(
    lambda ans, A, trailing_dim: lambda g: sum_trailing_antidiagonals(g))


def sum_antidiagonals(arr, labels, axis0, axis1, out_axis):
    old_labels = list(labels)
    labels = [l for l in labels if l not in (axis0, axis1)]
    arr = einsum1(arr, old_labels, labels + [axis0, axis1])

    reshaped_arr = np.reshape(
        arr, (-1, arr.shape[-2], arr.shape[-1]), order='C')
    ret = sum_trailing_antidiagonals(reshaped_arr)
    return np.reshape(ret, tuple(list(arr.shape[:-2]) + [-1]), order='C'), labels + [out_axis]

roll_trailing_axes = primitive(roll_trailing_axes)
unroll_trailing_axes = primitive(unroll_trailing_axes)

roll_trailing_axes.defgrad(lambda ans, A: lambda g: unroll_trailing_axes(g))
unroll_trailing_axes.defgrad(lambda ans, A: lambda g: roll_trailing_axes(g))


def roll_axes(arr, labels, axis0, axis1):
    tmp_labels = [l for l in labels if l not in (axis0, axis1)]
    tmp_labels += [axis0, axis1]

    arr = einsum1(arr, labels, tmp_labels)
    reshaped_arr = np.reshape(
        arr, (-1, arr.shape[-2], arr.shape[-1]), order='C')
    ret = roll_trailing_axes(reshaped_arr)
    ret = np.reshape(ret, tuple(list(arr.shape[:-1]) + [-1]), order='C')
    return einsum1(ret, tmp_labels, labels)

'''
Returns
-expi(-1/x) * exp(1/x) / x
for x s.t. abs(x) is decreasing
'''


def transformed_expi(x):
    abs_x = np.abs(x)
    ser = abs_x < 1. / 45.
    nser = np.logical_not(ser)

#     ret = np.zeros(x.shape)
#     ret[ser], ret[nser] = transformed_expi_series(x[ser]), transformed_expi_naive(x[nser])))
#     return ret

    # We use np.concatenate to combine.
    # would be better to use ret[ser] and ret[nser] as commented out above
    # but array assignment not yet supported by autograd
    assert np.all(abs_x[:-1] >= abs_x[1:])
    return np.concatenate((transformed_expi_naive(x[nser]), transformed_expi_series(x[ser])))


def transformed_expi_series(x):
    c_n, ret = 1., 1.
    for n in range(1, 11):
        c_n = -c_n * x * n
        ret = ret + c_n
    return ret


def transformed_expi_naive(x):
    return -expi(-1.0 / x) * np.exp(1.0 / x) / x


@primitive
def expi(x):
    return scipy.special.expi(x)
expi.defgrad(lambda ans, x: lambda g: g * np.exp(x) / x)

'''
returns (e^x-1)/x, for scalar x. works for x=0.
Taylor series is 1 + x/2! + x^2/3! + ...
'''


def expm1d(x):
    if x == 0.0:
        return expm1d_taylor(x)
    elif x == float('inf'):
        return float('inf')
    return np.expm1(x) / x
# used for higher order derivatives at x=0 and x=inf


def expm1d_taylor(x):
    c_n, ret = 1., 1.
    for n in range(2, 11):
        c_n = c_n * x / (1.0 * n)
        ret = ret + c_n
    return ret


def binom_coeffs(n):
    return scipy.misc.comb(n, np.arange(n + 1))

log_factorial = lambda n: scipy.special.gammaln(n + 1)
log_binom = lambda n, k: log_factorial(
    n) - log_factorial(k) - log_factorial(n - k)


def hypergeom_mat(N, n):
    K = np.outer(np.ones(n + 1), np.arange(N + 1))
    k = np.outer(np.arange(n + 1), np.ones(N + 1))
    ret = log_binom(K, k)
    ret = ret + ret[::-1, ::-1]
    ret = ret - log_binom(N, n)
    return np.exp(ret)


@memoize
def hypergeom_quasi_inverse(N, n):
    # return scipy.linalg.pinv(hypergeom_mat(N,n))
    # return np.linalg.pinv(hypergeom_mat(N,n))

    # pinv2 seems more numerically stable than alternatives
    # TODO: use randomized numerical linear algebra?
    return scipy.linalg.pinv2(hypergeom_mat(N, n))


@primitive
def symmetric_matrix(arr, n):
    if len(arr) != n * (n + 1) / 2:
        raise Exception("Array must have dimensions n*(n+1)/2")
    ret = np.zeros((n, n))
    idx = np.triu_indices(n)

    ret[idx] = arr
    ret[tuple(reversed(idx))] = arr

    assert np.all(ret == ret.T)
    return ret
symmetric_matrix.defgrad(lambda ans, arr, n: lambda g: g[np.triu_indices(n)])


def slogdet_pos(X):
    sgn, slogdet = np.linalg.slogdet(X)
    if sgn <= 0:
        raise Exception("X determinant is nonpositive")
    return slogdet


def log_wishart_pdf(X, V, n, p):
    # correct up to constant of proportionality
    return (n - p - 1) / 2 * slogdet_pos(X) - n / 2 * slogdet_pos(V) - 0.5 * np.trace(np.dot(np.linalg.inv(V), X))


def _apply_error_matrices(vecs, error_matrices):
    if not all([np.allclose(np.sum(err, axis=0), 1.0) for err in error_matrices]):
        raise Exception("Columns of error matrix should sum to 1")

    return [np.dot(v, err) for v, err in zip(vecs, error_matrices)]

# inverse of a PSD matrix


@primitive
def inv_psd(x, **tol_kwargs):
    x = check_psd(x, **tol_kwargs)
    return check_psd(scipy.linalg.pinvh(x), **tol_kwargs)
inv_psd.defgrad(lambda ans, x: lambda g: -np.dot(np.dot(ans, g), ans))
