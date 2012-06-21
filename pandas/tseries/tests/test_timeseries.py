# pylint: disable-msg=E1101,W0612
from __future__ import with_statement # for Python 2.5
import pandas.util.compat as itertools
from datetime import datetime, time, timedelta
import sys
import os
import unittest

import nose

import numpy as np
randn = np.random.randn

from pandas import (Index, Series, TimeSeries, DataFrame, isnull,
                    date_range, Timestamp, DatetimeIndex, Int64Index,
                    to_datetime, bdate_range)

from pandas.core.daterange import DateRange
import pandas.core.datetools as datetools
import pandas.tseries.offsets as offsets
import pandas.tseries.frequencies as fmod

from pandas.util.testing import assert_series_equal, assert_almost_equal
import pandas.util.testing as tm

from pandas.lib import NaT, iNaT
import pandas.lib as lib
import cPickle as pickle
import pandas.core.datetools as dt
from numpy.random import rand
from pandas.util.testing import assert_frame_equal
import pandas.util.py3compat as py3compat
from pandas.core.datetools import BDay
import pandas.core.common as com


class TestTimeSeriesDuplicates(unittest.TestCase):

    def setUp(self):
        dates = [datetime(2000, 1, 2), datetime(2000, 1, 2),
                 datetime(2000, 1, 2), datetime(2000, 1, 3),
                 datetime(2000, 1, 3), datetime(2000, 1, 3),
                 datetime(2000, 1, 4), datetime(2000, 1, 4),
                 datetime(2000, 1, 4), datetime(2000, 1, 5)]

        self.dups = Series(np.random.randn(len(dates)), index=dates)

    def test_constructor(self):
        self.assert_(isinstance(self.dups, TimeSeries))
        self.assert_(isinstance(self.dups.index, DatetimeIndex))

    def test_is_unique_monotonic(self):
        self.assert_(not self.dups.index.is_unique)

    def test_index_unique(self):
        uniques = self.dups.index.unique()
        self.assert_(uniques.dtype == 'M8[ns]') # sanity

    def test_duplicate_dates_indexing(self):
        ts = self.dups

        uniques = ts.index.unique()
        for date in uniques:
            result = ts[date]

            mask = ts.index == date
            total = (ts.index == date).sum()
            expected = ts[mask]
            if total > 1:
                assert_series_equal(result, expected)
            else:
                assert_almost_equal(result, expected[0])

            cp = ts.copy()
            cp[date] = 0
            expected = Series(np.where(mask, 0, ts), index=ts.index)
            assert_series_equal(cp, expected)

        self.assertRaises(KeyError, ts.__getitem__, datetime(2000, 1, 6))
        self.assertRaises(KeyError, ts.__setitem__, datetime(2000, 1, 6), 0)

    def test_range_slice(self):
        idx = DatetimeIndex(['1/1/2000', '1/2/2000', '1/2/2000', '1/3/2000',
                             '1/4/2000'])

        ts = Series(np.random.randn(len(idx)), index=idx)

        result = ts['1/2/2000':]
        expected = ts[1:]
        assert_series_equal(result, expected)

        result = ts['1/2/2000':'1/3/2000']
        expected = ts[1:4]
        assert_series_equal(result, expected)

    def test_groupby_average_dup_values(self):
        result = self.dups.groupby(level=0).mean()
        expected = self.dups.groupby(self.dups.index).mean()
        assert_series_equal(result, expected)


def assert_range_equal(left, right):
    assert(left.equals(right))
    assert(left.freq == right.freq)
    assert(left.tz == right.tz)


def _skip_if_no_pytz():
    try:
        import pytz
    except ImportError:
        raise nose.SkipTest


class TestTimeSeries(unittest.TestCase):

    def test_dti_slicing(self):
        dti = DatetimeIndex(start='1/1/2005', end='12/1/2005', freq='M')
        dti2 = dti[[1,3,5]]

        v1 = dti2[0]
        v2 = dti2[1]
        v3 = dti2[2]

        self.assertEquals(v1, Timestamp('2/28/2005'))
        self.assertEquals(v2, Timestamp('4/30/2005'))
        self.assertEquals(v3, Timestamp('6/30/2005'))

        # don't carry freq through irregular slicing
        self.assert_(dti2.freq is None)

    def test_pass_datetimeindex_to_index(self):
        # Bugs in #1396

        rng = date_range('1/1/2000', '3/1/2000')
        idx = Index(rng, dtype=object)

        expected = Index(rng.to_pydatetime(), dtype=object)

        self.assert_(np.array_equal(idx.values, expected.values))

    def test_contiguous_boolean_preserve_freq(self):
        rng = date_range('1/1/2000', '3/1/2000', freq='B')

        mask = np.zeros(len(rng), dtype=bool)
        mask[10:20] = True

        masked = rng[mask]
        expected = rng[10:20]
        self.assert_(expected.freq is not None)
        assert_range_equal(masked, expected)

        mask[22] = True
        masked = rng[mask]
        self.assert_(masked.freq is None)

    def test_getitem_median_slice_bug(self):
        index = date_range('20090415', '20090519', freq='2B')
        s = Series(np.random.randn(13), index=index)

        indexer = [slice(6, 7, None)]
        result = s[indexer]
        expected = s[indexer[0]]
        assert_series_equal(result, expected)

    def test_series_box_timestamp(self):
        rng = date_range('20090415', '20090519', freq='B')
        s = Series(rng)

        self.assert_(isinstance(s[5], Timestamp))

        rng = date_range('20090415', '20090519', freq='B')
        s = Series(rng, index=rng)
        self.assert_(isinstance(s[5], Timestamp))

    def test_timestamp_to_datetime(self):
        _skip_if_no_pytz()
        rng = date_range('20090415', '20090519',
                         tz='US/Eastern')

        stamp = rng[0]
        dtval = stamp.to_pydatetime()
        self.assertEquals(stamp, dtval)
        self.assertEquals(stamp.tzinfo, dtval.tzinfo)

    def test_index_convert_to_datetime_array(self):
        _skip_if_no_pytz()

        def _check_rng(rng):
            converted = rng.to_pydatetime()
            self.assert_(isinstance(converted, np.ndarray))
            for x, stamp in zip(converted, rng):
                self.assert_(type(x) is datetime)
                self.assertEquals(x, stamp.to_pydatetime())
                self.assertEquals(x.tzinfo, stamp.tzinfo)

        rng = date_range('20090415', '20090519')
        rng_eastern = date_range('20090415', '20090519', tz='US/Eastern')
        rng_utc = date_range('20090415', '20090519', tz='utc')

        _check_rng(rng)
        _check_rng(rng_eastern)
        _check_rng(rng_utc)

    def test_series_ctor_plus_datetimeindex(self):
        rng = date_range('20090415', '20090519', freq='B')
        data = dict((k, 1) for k in rng)

        result = Series(data, index=rng)
        self.assert_(result.index is rng)

    def test_series_pad_backfill_limit(self):
        index = np.arange(10)
        s = Series(np.random.randn(10), index=index)

        result = s[:2].reindex(index, method='pad', limit=5)

        expected = s[:2].reindex(index).fillna(method='pad')
        expected[-3:] = np.nan
        assert_series_equal(result, expected)

        result = s[-2:].reindex(index, method='backfill', limit=5)

        expected = s[-2:].reindex(index).fillna(method='backfill')
        expected[:3] = np.nan
        assert_series_equal(result, expected)

    def test_series_fillna_limit(self):
        index = np.arange(10)
        s = Series(np.random.randn(10), index=index)

        result = s[:2].reindex(index)
        result = result.fillna(method='pad', limit=5)

        expected = s[:2].reindex(index).fillna(method='pad')
        expected[-3:] = np.nan
        assert_series_equal(result, expected)

        result = s[-2:].reindex(index)
        result = result.fillna(method='bfill', limit=5)

        expected = s[-2:].reindex(index).fillna(method='backfill')
        expected[:3] = np.nan
        assert_series_equal(result, expected)

    def test_frame_pad_backfill_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.randn(10, 4), index=index)

        result = df[:2].reindex(index, method='pad', limit=5)

        expected = df[:2].reindex(index).fillna(method='pad')
        expected.values[-3:] = np.nan
        tm.assert_frame_equal(result, expected)

        result = df[-2:].reindex(index, method='backfill', limit=5)

        expected = df[-2:].reindex(index).fillna(method='backfill')
        expected.values[:3] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_frame_fillna_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.randn(10, 4), index=index)

        result = df[:2].reindex(index)
        result = result.fillna(method='pad', limit=5)

        expected = df[:2].reindex(index).fillna(method='pad')
        expected.values[-3:] = np.nan
        tm.assert_frame_equal(result, expected)

        result = df[-2:].reindex(index)
        result = result.fillna(method='backfill', limit=5)

        expected = df[-2:].reindex(index).fillna(method='backfill')
        expected.values[:3] = np.nan
        tm.assert_frame_equal(result, expected)

    def test_sparse_series_fillna_limit(self):
        index = np.arange(10)
        s = Series(np.random.randn(10), index=index)

        ss = s[:2].reindex(index).to_sparse()
        result = ss.fillna(method='pad', limit=5)
        expected = ss.fillna(method='pad', limit=5)
        expected = expected.to_dense()
        expected[-3:] = np.nan
        expected = expected.to_sparse()
        assert_series_equal(result, expected)

        ss = s[-2:].reindex(index).to_sparse()
        result = ss.fillna(method='backfill', limit=5)
        expected = ss.fillna(method='backfill')
        expected = expected.to_dense()
        expected[:3] = np.nan
        expected = expected.to_sparse()
        assert_series_equal(result, expected)

    def test_sparse_series_pad_backfill_limit(self):
        index = np.arange(10)
        s = Series(np.random.randn(10), index=index)
        s = s.to_sparse()

        result = s[:2].reindex(index, method='pad', limit=5)
        expected = s[:2].reindex(index).fillna(method='pad')
        expected = expected.to_dense()
        expected[-3:] = np.nan
        expected = expected.to_sparse()
        assert_series_equal(result, expected)

        result = s[-2:].reindex(index, method='backfill', limit=5)
        expected = s[-2:].reindex(index).fillna(method='backfill')
        expected = expected.to_dense()
        expected[:3] = np.nan
        expected = expected.to_sparse()
        assert_series_equal(result, expected)

    def test_sparse_frame_pad_backfill_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.randn(10, 4), index=index)
        sdf = df.to_sparse()

        result = sdf[:2].reindex(index, method='pad', limit=5)

        expected = sdf[:2].reindex(index).fillna(method='pad')
        expected = expected.to_dense()
        expected.values[-3:] = np.nan
        expected = expected.to_sparse()
        tm.assert_frame_equal(result, expected)

        result = sdf[-2:].reindex(index, method='backfill', limit=5)

        expected = sdf[-2:].reindex(index).fillna(method='backfill')
        expected = expected.to_dense()
        expected.values[:3] = np.nan
        expected = expected.to_sparse()
        tm.assert_frame_equal(result, expected)

    def test_sparse_frame_fillna_limit(self):
        index = np.arange(10)
        df = DataFrame(np.random.randn(10, 4), index=index)
        sdf = df.to_sparse()

        result = sdf[:2].reindex(index)
        result = result.fillna(method='pad', limit=5)

        expected = sdf[:2].reindex(index).fillna(method='pad')
        expected = expected.to_dense()
        expected.values[-3:] = np.nan
        expected = expected.to_sparse()
        tm.assert_frame_equal(result, expected)

        result = sdf[-2:].reindex(index)
        result = result.fillna(method='backfill', limit=5)

        expected = sdf[-2:].reindex(index).fillna(method='backfill')
        expected = expected.to_dense()
        expected.values[:3] = np.nan
        expected = expected.to_sparse()
        tm.assert_frame_equal(result, expected)

    def test_pad_require_monotonicity(self):
        rng = date_range('1/1/2000', '3/1/2000', freq='B')

        rng2 = rng[::2][::-1]

        self.assertRaises(AssertionError, rng2.get_indexer, rng,
                          method='pad')

    def test_frame_ctor_datetime64_column(self):
        rng = date_range('1/1/2000 00:00:00', '1/1/2000 1:59:50',
                         freq='10s')
        dates = np.asarray(rng)

        df = DataFrame({'A': np.random.randn(len(rng)), 'B': dates})
        self.assert_(np.issubdtype(df['B'].dtype, np.dtype('M8[ns]')))

    def test_frame_add_datetime64_column(self):
        rng = date_range('1/1/2000 00:00:00', '1/1/2000 1:59:50',
                         freq='10s')
        df = DataFrame(index=np.arange(len(rng)))

        df['A'] = rng
        self.assert_(np.issubdtype(df['A'].dtype, np.dtype('M8[ns]')))

    def test_frame_add_datetime64_col_other_units(self):
        n = 100

        units = ['h', 'm', 's', 'ms', 'D', 'M', 'Y']

        ns_dtype = np.dtype('M8[ns]')

        for unit in units:
            dtype = np.dtype('M8[%s]' % unit)
            vals = np.arange(n, dtype=np.int64).view(dtype)

            df = DataFrame({'ints' : np.arange(n)}, index=np.arange(n))
            df[unit] = vals

            ex_vals = to_datetime(vals.astype('O'))

            self.assert_(df[unit].dtype == ns_dtype)
            self.assert_((df[unit].values == ex_vals).all())

        # Test insertion into existing datetime64 column
        df = DataFrame({'ints' : np.arange(n)}, index=np.arange(n))
        df['dates'] = np.arange(n, dtype=np.int64).view(ns_dtype)

        for unit in units:
            dtype = np.dtype('M8[%s]' % unit)
            vals = np.arange(n, dtype=np.int64).view(dtype)

            tmp = df.copy()

            tmp['dates'] = vals
            ex_vals = to_datetime(vals.astype('O'))

            self.assert_((tmp['dates'].values == ex_vals).all())

    def test_series_ctor_datetime64(self):
        rng = date_range('1/1/2000 00:00:00', '1/1/2000 1:59:50',
                         freq='10s')
        dates = np.asarray(rng)

        series = Series(dates)
        self.assert_(np.issubdtype(series.dtype, np.dtype('M8[ns]')))

    def test_index_cast_datetime64_other_units(self):
        arr = np.arange(0, 100, 10, dtype=np.int64).view('M8[D]')

        idx = Index(arr)

        self.assert_((idx.values == lib.cast_to_nanoseconds(arr)).all())

    def test_index_astype_datetime64(self):
        idx = Index([datetime(2012, 1, 1)], dtype=object)

        if np.__version__ >= '1.7':
            raise nose.SkipTest

        casted = idx.astype(np.dtype('M8[D]'))
        expected = DatetimeIndex(idx.values)
        self.assert_(isinstance(casted, DatetimeIndex))
        self.assert_(casted.equals(expected))

    def test_reindex_series_add_nat(self):
        rng = date_range('1/1/2000 00:00:00', periods=10, freq='10s')
        series = Series(rng)

        result = series.reindex(range(15))
        self.assert_(np.issubdtype(result.dtype, np.dtype('M8[ns]')))

        mask = result.isnull()
        self.assert_(mask[-5:].all())
        self.assert_(not mask[:-5].any())

    def test_reindex_frame_add_nat(self):
        rng = date_range('1/1/2000 00:00:00', periods=10, freq='10s')
        df = DataFrame({'A': np.random.randn(len(rng)), 'B': rng})

        result = df.reindex(range(15))
        self.assert_(np.issubdtype(result['B'].dtype, np.dtype('M8[ns]')))

        mask = com.isnull(result)['B']
        self.assert_(mask[-5:].all())
        self.assert_(not mask[:-5].any())

    def test_series_repr_nat(self):
        series = Series([0, 1000, 2000, iNaT], dtype='M8[ns]')

        result = repr(series)
        expected = ('0          1970-01-01 00:00:00\n'
                    '1   1970-01-01 00:00:00.000001\n'
                    '2   1970-01-01 00:00:00.000002\n'
                    '3                          NaT')
        self.assertEquals(result, expected)

    def test_fillna_nat(self):
        series = Series([0, 1, 2, iNaT], dtype='M8[ns]')

        filled = series.fillna(method='pad')
        filled2 = series.fillna(value=series.values[2])

        expected = series.copy()
        expected.values[3] = expected.values[2]

        assert_series_equal(filled, expected)
        assert_series_equal(filled2, expected)

        df = DataFrame({'A': series})
        filled = df.fillna(method='pad')
        filled2 = df.fillna(value=series.values[2])
        expected = DataFrame({'A': expected})
        assert_frame_equal(filled, expected)
        assert_frame_equal(filled2, expected)


        series = Series([iNaT, 0, 1, 2], dtype='M8[ns]')

        filled = series.fillna(method='bfill')
        filled2 = series.fillna(value=series[1])

        expected = series.copy()
        expected[0] = expected[1]

        assert_series_equal(filled, expected)
        assert_series_equal(filled2, expected)

        df = DataFrame({'A': series})
        filled = df.fillna(method='bfill')
        filled2 = df.fillna(value=series[1])
        expected = DataFrame({'A': expected})
        assert_frame_equal(filled, expected)
        assert_frame_equal(filled2, expected)

    def test_string_na_nat_conversion(self):
        # GH #999, #858

        from dateutil.parser import parse

        strings = np.array(['1/1/2000', '1/2/2000', np.nan,
                            '1/4/2000, 12:34:56'], dtype=object)

        expected = np.empty(4, dtype='M8[ns]')
        for i, val in enumerate(strings):
            if com.isnull(val):
                expected[i] = iNaT
            else:
                expected[i] = parse(val)

        result = lib.array_to_datetime(strings)
        assert_almost_equal(result, expected)

        result2 = to_datetime(strings)
        self.assert_(isinstance(result2, DatetimeIndex))
        assert_almost_equal(result, result2)

        malformed = np.array(['1/100/2000', np.nan], dtype=object)
        result = to_datetime(malformed)
        assert_almost_equal(result, malformed)

        self.assertRaises(ValueError, to_datetime, malformed,
                          errors='raise')

        idx = ['a', 'b', 'c', 'd', 'e']
        series = Series(['1/1/2000', np.nan, '1/3/2000', np.nan,
                         '1/5/2000'], index=idx, name='foo')
        dseries = Series([to_datetime('1/1/2000'), np.nan,
                          to_datetime('1/3/2000'), np.nan,
                          to_datetime('1/5/2000')], index=idx, name='foo')

        result = to_datetime(series)
        dresult = to_datetime(dseries)

        expected = Series(np.empty(5, dtype='M8[ns]'), index=idx)
        for i in range(5):
            x = series[i]
            if isnull(x):
                expected[i] = iNaT
            else:
                expected[i] = to_datetime(x)

        assert_series_equal(result, expected)
        self.assertEquals(result.name, 'foo')

        assert_series_equal(dresult, expected)
        self.assertEquals(dresult.name, 'foo')

    def test_nat_vector_field_access(self):
        idx = DatetimeIndex(['1/1/2000', None, None, '1/4/2000'])

        fields = ['year', 'quarter', 'month', 'day', 'hour',
                  'minute', 'second', 'microsecond', 'nanosecond',
                  'week', 'dayofyear']
        for field in fields:
            result = getattr(idx, field)
            expected = [getattr(x, field) if x is not NaT else -1
                        for x in idx]
            self.assert_(np.array_equal(result, expected))

    def test_nat_scalar_field_access(self):
        fields = ['year', 'quarter', 'month', 'day', 'hour',
                  'minute', 'second', 'microsecond', 'nanosecond',
                  'week', 'dayofyear']
        for field in fields:
            result = getattr(NaT, field)
            self.assertEquals(result, -1)

        self.assertEquals(NaT.weekday(), -1)

    def test_to_datetime_empty_string(self):
        result = to_datetime('')
        self.assert_(result == '')

        result = to_datetime(['', ''])
        self.assert_(isnull(result).all())

    def test_to_datetime_other_datetime64_units(self):
        # 5/25/2012
        scalar = np.int64(1337904000000000).view('M8[us]')
        as_obj = scalar.astype('O')

        index = DatetimeIndex([scalar])
        self.assertEquals(index[0], scalar.astype('O'))

        value = Timestamp(scalar)
        self.assertEquals(value, as_obj)

    def test_to_datetime_list_of_integers(self):
        rng = date_range('1/1/2000', periods=20)
        rng = DatetimeIndex(rng.values)

        ints = list(rng.asi8)

        result = DatetimeIndex(ints)

        self.assert_(rng.equals(result))

    def test_index_to_datetime(self):
        idx = Index(['1/1/2000', '1/2/2000', '1/3/2000'])

        result = idx.to_datetime()
        expected = DatetimeIndex(datetools.to_datetime(idx.values))
        self.assert_(result.equals(expected))

        today = datetime.today()
        idx = Index([today], dtype=object)
        result = idx.to_datetime()
        expected = DatetimeIndex([today])
        self.assert_(result.equals(expected))

    def test_to_datetime_freq(self):
        xp = bdate_range('2000-1-1', periods=10, tz='UTC')
        rs = xp.to_datetime()
        self.assert_(xp.freq == rs.freq)
        self.assert_(xp.tzinfo == rs.tzinfo)

    def test_range_misspecified(self):
        # GH #1095

        self.assertRaises(ValueError, date_range, '1/1/2000')
        self.assertRaises(ValueError, date_range, end='1/1/2000')
        self.assertRaises(ValueError, date_range, periods=10)

        self.assertRaises(ValueError, date_range, '1/1/2000', freq='H')
        self.assertRaises(ValueError, date_range, end='1/1/2000', freq='H')
        self.assertRaises(ValueError, date_range, periods=10, freq='H')

    def test_reasonable_keyerror(self):
        # GH #1062
        index = DatetimeIndex(['1/3/2000'])
        try:
            index.get_loc('1/1/2000')
        except KeyError, e:
            self.assert_('2000' in str(e))

    def test_reindex_with_datetimes(self):
        rng = date_range('1/1/2000', periods=20)
        ts = Series(np.random.randn(20), index=rng)

        result = ts.reindex(list(ts.index[5:10]))
        expected = ts[5:10]
        tm.assert_series_equal(result, expected)

        result = ts[list(ts.index[5:10])]
        tm.assert_series_equal(result, expected)

    def test_promote_datetime_date(self):
        rng = date_range('1/1/2000', periods=20)
        ts = Series(np.random.randn(20), index=rng)

        ts_slice = ts[5:]
        ts2 = ts_slice.copy()
        ts2.index = [x.date() for x in ts2.index]

        result = ts + ts2
        result2 = ts2 + ts
        expected = ts + ts[5:]
        assert_series_equal(result, expected)
        assert_series_equal(result2, expected)

        # test asfreq
        result = ts2.asfreq('4H', method='ffill')
        expected = ts[5:].asfreq('4H', method='ffill')
        assert_series_equal(result, expected)

        result = rng.get_indexer(ts2.index)
        expected = rng.get_indexer(ts_slice.index)
        self.assert_(np.array_equal(result, expected))

    def test_date_range_gen_error(self):
        rng = date_range('1/1/2000 00:00', '1/1/2000 00:18', freq='5min')
        self.assertEquals(len(rng), 4)

    def test_first_subset(self):
        ts = _simple_ts('1/1/2000', '1/1/2010', freq='12h')
        result = ts.first('10d')
        self.assert_(len(result) == 20)

        ts = _simple_ts('1/1/2000', '1/1/2010')
        result = ts.first('10d')
        self.assert_(len(result) == 10)

        result = ts.first('3M')
        expected = ts[:'3/31/2000']
        assert_series_equal(result, expected)

        result = ts.first('21D')
        expected = ts[:21]
        assert_series_equal(result, expected)

        result = ts[:0].first('3M')
        assert_series_equal(result, ts[:0])

    def test_last_subset(self):
        ts = _simple_ts('1/1/2000', '1/1/2010', freq='12h')
        result = ts.last('10d')
        self.assert_(len(result) == 20)

        ts = _simple_ts('1/1/2000', '1/1/2010')
        result = ts.last('10d')
        self.assert_(len(result) == 10)

        result = ts.last('21D')
        expected = ts['12/12/2009':]
        assert_series_equal(result, expected)

        result = ts.last('21D')
        expected = ts[-21:]
        assert_series_equal(result, expected)

        result = ts[:0].last('3M')
        assert_series_equal(result, ts[:0])

    def test_add_offset(self):
        rng = date_range('1/1/2000', '2/1/2000')

        result = rng + offsets.Hour(2)
        expected = date_range('1/1/2000 02:00', '2/1/2000 02:00')
        self.assert_(result.equals(expected))

    def test_format_pre_1900_dates(self):
        rng = date_range('1/1/1850', '1/1/1950', freq='A-DEC')
        rng.format()
        ts = Series(1, index=rng)
        repr(ts)

    def test_repeat(self):
        rng = date_range('1/1/2000', '1/1/2001')

        result = rng.repeat(5)
        self.assert_(result.freq is None)
        self.assert_(len(result) == 5 * len(rng))

    def test_at_time(self):
        rng = date_range('1/1/2000', '1/5/2000', freq='5min')
        ts = Series(np.random.randn(len(rng)), index=rng)
        rs = ts.at_time(rng[1])
        self.assert_((rs.index.hour == rng[1].hour).all())
        self.assert_((rs.index.minute == rng[1].minute).all())
        self.assert_((rs.index.second == rng[1].second).all())

        result = ts.at_time('9:30')
        expected = ts.at_time(time(9, 30))
        assert_series_equal(result, expected)

        df = DataFrame(np.random.randn(len(rng), 3), index=rng)

        result = ts[time(9, 30)]
        result_df = df.ix[time(9, 30)]
        expected = ts[(rng.hour == 9) & (rng.minute == 30)]
        exp_df = df[(rng.hour == 9) & (rng.minute == 30)]

        # expected.index = date_range('1/1/2000', '1/4/2000')

        assert_series_equal(result, expected)
        tm.assert_frame_equal(result_df, exp_df)

        chunk = df.ix['1/4/2000':]
        result = chunk.ix[time(9, 30)]
        expected = result_df[-1:]
        tm.assert_frame_equal(result, expected)

        # midnight, everything
        rng = date_range('1/1/2000', '1/31/2000')
        ts = Series(np.random.randn(len(rng)), index=rng)

        result = ts.at_time(time(0, 0))
        assert_series_equal(result, ts)

        # time doesn't exist
        rng = date_range('1/1/2012', freq='23Min', periods=384)
        ts = Series(np.random.randn(len(rng)), rng)
        rs = ts.at_time('16:00')
        self.assert_(len(rs) == 0)

    def test_between_time(self):
        rng = date_range('1/1/2000', '1/5/2000', freq='5min')
        ts = Series(np.random.randn(len(rng)), index=rng)
        stime = time(0, 0)
        etime = time(1, 0)

        close_open = itertools.product([True, False], [True, False])
        for inc_start, inc_end in close_open:
            filtered = ts.between_time(stime, etime, inc_start, inc_end)
            exp_len = 13 * 4 + 1
            if not inc_start:
                exp_len -= 5
            if not inc_end:
                exp_len -= 4

            self.assert_(len(filtered) == exp_len)
            for rs in filtered.index:
                t = rs.time()
                if inc_start:
                    self.assert_(t >= stime)
                else:
                    self.assert_(t > stime)

                if inc_end:
                    self.assert_(t <= etime)
                else:
                    self.assert_(t < etime)

        result = ts.between_time('00:00', '01:00')
        expected = ts.between_time(stime, etime)
        assert_series_equal(result, expected)

    def test_dti_constructor_preserve_dti_freq(self):
        rng = date_range('1/1/2000', '1/2/2000', freq='5min')

        rng2 = DatetimeIndex(rng)
        self.assert_(rng.freq == rng2.freq)

    def test_normalize(self):
        rng = date_range('1/1/2000 9:30', periods=10, freq='D')

        result = rng.normalize()
        expected = date_range('1/1/2000', periods=10, freq='D')
        self.assert_(result.equals(expected))

        self.assert_(result.is_normalized)
        self.assert_(not rng.is_normalized)

    def test_to_period(self):
        from pandas.tseries.period import period_range

        ts = _simple_ts('1/1/2000', '1/1/2001')

        pts = ts.to_period()
        exp = ts.copy()
        exp.index = period_range('1/1/2000', '1/1/2001')
        assert_series_equal(pts, exp)

        pts = ts.to_period('M')
        self.assert_(pts.index.equals(exp.index.asfreq('M')))

    def test_frame_to_period(self):
        K = 5
        from pandas.tseries.period import period_range

        dr = date_range('1/1/2000', '1/1/2001')
        pr = period_range('1/1/2000', '1/1/2001')
        df = DataFrame(randn(len(dr), K), index=dr)
        df['mix'] = 'a'

        pts = df.to_period()
        exp = df.copy()
        exp.index = pr
        assert_frame_equal(pts, exp)

        pts = df.to_period('M')
        self.assert_(pts.index.equals(exp.index.asfreq('M')))

        df = df.T
        pts = df.to_period(axis=1)
        exp = df.copy()
        exp.columns = pr
        assert_frame_equal(pts, exp)

        pts = df.to_period('M', axis=1)
        self.assert_(pts.columns.equals(exp.columns.asfreq('M')))

        self.assertRaises(ValueError, df.to_period, axis=2)

    def test_timestamp_fields(self):
        # extra fields from DatetimeIndex like quarter and week
        from pandas.lib import Timestamp
        idx = tm.makeDateIndex(10)

        fields = ['dayofweek', 'dayofyear', 'week', 'weekofyear', 'quarter']
        for f in fields:
            expected = getattr(idx, f)[0]
            result = getattr(Timestamp(idx[0]), f)
            self.assertEqual(result, expected)

        self.assertEqual(idx.freq, Timestamp(idx[0], idx.freq).freq)
        self.assertEqual(idx.freqstr, Timestamp(idx[0], idx.freq).freqstr)

    def test_timestamp_date_out_of_range(self):
        self.assertRaises(ValueError, Timestamp, '1676-01-01')
        self.assertRaises(ValueError, Timestamp, '2263-01-01')

        # 1475
        self.assertRaises(ValueError, DatetimeIndex, ['1400-01-01'])
        self.assertRaises(ValueError, DatetimeIndex, [datetime(1400, 1, 1)])

    def test_timestamp_repr(self):
        # pre-1900
        stamp = Timestamp('1850-01-01', tz='US/Eastern')
        repr(stamp)

        iso8601 = '1850-01-01 01:23:45.012345'
        stamp = Timestamp(iso8601, tz='US/Eastern')
        result = repr(stamp)
        self.assert_(iso8601 in result)

    def test_datetimeindex_integers_shift(self):
        rng = date_range('1/1/2000', periods=20)

        result = rng + 5
        expected = rng.shift(5)
        self.assert_(result.equals(expected))

        result = rng - 5
        expected = rng.shift(-5)
        self.assert_(result.equals(expected))

    def test_astype_object(self):
        # NumPy 1.6.1 weak ns support
        rng = date_range('1/1/2000', periods=20)

        casted = rng.astype('O')
        exp_values = list(rng)

        self.assert_(np.array_equal(casted, exp_values))

    def test_catch_infinite_loop(self):
        offset = datetools.DateOffset(minute=5)
        # blow up, don't loop forever
        self.assertRaises(Exception, date_range, datetime(2011,11,11),
                          datetime(2011,11,12), freq=offset)

    def test_append_concat(self):
        rng = date_range('5/8/2012 1:45', periods=10, freq='5T')
        ts = Series(np.random.randn(len(rng)), rng)
        df = DataFrame(np.random.randn(len(rng), 4), index=rng)

        result = ts.append(ts)
        result_df = df.append(df)
        ex_index = DatetimeIndex(np.tile(rng.values, 2))
        self.assert_(result.index.equals(ex_index))
        self.assert_(result_df.index.equals(ex_index))

        appended = rng.append(rng)
        self.assert_(appended.equals(ex_index))

        appended = rng.append([rng, rng])
        ex_index = DatetimeIndex(np.tile(rng.values, 3))
        self.assert_(appended.equals(ex_index))

        # different index names
        rng1 = rng.copy()
        rng2 = rng.copy()
        rng1.name = 'foo'
        rng2.name = 'bar'
        self.assert_(rng1.append(rng1).name == 'foo')
        self.assert_(rng1.append(rng2).name is None)

    def test_set_dataframe_column_ns_dtype(self):
        x = DataFrame([datetime.now(), datetime.now()])
        self.assert_(x[0].dtype == object)

        x[0] = to_datetime(x[0])
        self.assert_(x[0].dtype == np.dtype('M8[ns]'))

    def test_groupby_count_dateparseerror(self):
        dr = date_range(start='1/1/2012', freq='5min', periods=10)

        # BAD Example, datetimes first
        s = Series(np.arange(10), index=[dr, range(10)])
        grouped = s.groupby(lambda x: x[1] % 2 == 0)
        result = grouped.count()

        s = Series(np.arange(10), index=[range(10), dr])
        grouped = s.groupby(lambda x: x[0] % 2 == 0)
        expected = grouped.count()

        assert_series_equal(result, expected)


def _simple_ts(start, end, freq='D'):
    rng = date_range(start, end, freq=freq)
    return Series(np.random.randn(len(rng)), index=rng)


class TestDatetimeIndex(unittest.TestCase):

    def test_append_join_nondatetimeindex(self):
        rng = date_range('1/1/2000', periods=10)
        idx = Index(['a', 'b', 'c', 'd'])

        result = rng.append(idx)
        self.assert_(isinstance(result[0], Timestamp))

        # it works
        rng.join(idx, how='outer')

    def test_astype(self):
        rng = date_range('1/1/2000', periods=10)

        result = rng.astype('i8')
        self.assert_(np.array_equal(result, rng.asi8))

    def test_to_period_nofreq(self):
        idx = DatetimeIndex(['2000-01-01', '2000-01-02', '2000-01-04'])
        self.assertRaises(ValueError, idx.to_period)

        idx = DatetimeIndex(['2000-01-01', '2000-01-02', '2000-01-03'],
                            freq='infer')
        idx.to_period()

    def test_constructor_coverage(self):
        rng = date_range('1/1/2000', periods=10.5)
        exp = date_range('1/1/2000', periods=10)
        self.assert_(rng.equals(exp))

        self.assertRaises(ValueError, DatetimeIndex, start='1/1/2000',
                          periods='foo', freq='D')

        self.assertRaises(ValueError, DatetimeIndex, start='1/1/2000',
                          end='1/10/2000')

        self.assertRaises(ValueError, DatetimeIndex, '1/1/2000')

        # generator expression
        gen = (datetime(2000, 1, 1) + timedelta(i) for i in range(10))
        result = DatetimeIndex(gen)
        expected = DatetimeIndex([datetime(2000, 1, 1) + timedelta(i)
                                  for i in range(10)])
        self.assert_(result.equals(expected))

        # NumPy string array
        strings = np.array(['2000-01-01', '2000-01-02', '2000-01-03'])
        result = DatetimeIndex(strings)
        expected = DatetimeIndex(strings.astype('O'))
        self.assert_(result.equals(expected))

        from_ints = DatetimeIndex(expected.asi8)
        self.assert_(from_ints.equals(expected))

        # non-conforming
        self.assertRaises(ValueError, DatetimeIndex,
                          ['2000-01-01', '2000-01-02', '2000-01-04'],
                          freq='D')

        self.assertRaises(ValueError, DatetimeIndex,
                          start='2011-01-01', freq='b')
        self.assertRaises(ValueError, DatetimeIndex,
                          end='2011-01-01', freq='B')
        self.assertRaises(ValueError, DatetimeIndex, periods=10, freq='D')

    def test_comparisons_coverage(self):
        rng = date_range('1/1/2000', periods=10)

        # raise TypeError for now
        self.assertRaises(TypeError, rng.__lt__, rng[3].value)

        result = rng == list(rng)
        exp = rng == rng
        self.assert_(np.array_equal(result, exp))

    def test_map(self):
        rng = date_range('1/1/2000', periods=10)

        f = lambda x: x.strftime('%Y%m%d')
        result = rng.map(f)
        exp = [f(x) for x in rng]
        self.assert_(np.array_equal(result, exp))

    def test_add_union(self):
        rng = date_range('1/1/2000', periods=5)
        rng2 = date_range('1/6/2000', periods=5)

        result = rng + rng2
        expected = rng.union(rng2)
        self.assert_(result.equals(expected))

    def test_misc_coverage(self):
        rng = date_range('1/1/2000', periods=5)
        result = rng.groupby(rng.day)
        self.assert_(isinstance(result.values()[0][0], Timestamp))

        idx = DatetimeIndex(['2000-01-03', '2000-01-01', '2000-01-02'])
        self.assert_(idx.equals(list(idx)))

        non_datetime = Index(list('abc'))
        self.assert_(not idx.equals(list(non_datetime)))

    def test_union_coverage(self):
        idx = DatetimeIndex(['2000-01-03', '2000-01-01', '2000-01-02'])
        ordered = DatetimeIndex(idx.order(), freq='infer')
        result = ordered.union(idx)
        self.assert_(result.equals(ordered))

        result = ordered[:0].union(ordered)
        self.assert_(result.equals(ordered))
        self.assert_(result.freq == ordered.freq)

    # def test_add_timedelta64(self):
    #     rng = date_range('1/1/2000', periods=5)
    #     delta = rng.values[3] - rng.values[1]

    #     result = rng + delta
    #     expected = rng + timedelta(2)
    #     self.assert_(result.equals(expected))

    def test_get_duplicates(self):
        idx = DatetimeIndex(['2000-01-01', '2000-01-02', '2000-01-02',
                             '2000-01-03', '2000-01-03', '2000-01-04'])

        result = idx.get_duplicates()
        ex = DatetimeIndex(['2000-01-02', '2000-01-03'])
        self.assert_(result.equals(ex))

    def test_argmin_argmax(self):
        idx = DatetimeIndex(['2000-01-04', '2000-01-01', '2000-01-02'])
        self.assertEqual(idx.argmin(), 1)
        self.assertEqual(idx.argmax(), 0)

    def test_order(self):
        idx = DatetimeIndex(['2000-01-04', '2000-01-01', '2000-01-02'])

        ordered = idx.order()
        self.assert_(ordered.is_monotonic)

        ordered = idx.order(ascending=False)
        self.assert_(ordered[::-1].is_monotonic)

        ordered, dexer = idx.order(return_indexer=True)
        self.assert_(ordered.is_monotonic)
        self.assert_(np.array_equal(dexer, [1, 2, 0]))

        ordered, dexer = idx.order(return_indexer=True, ascending=False)
        self.assert_(ordered[::-1].is_monotonic)
        self.assert_(np.array_equal(dexer, [0, 2, 1]))

    def test_insert(self):
        idx = DatetimeIndex(['2000-01-04', '2000-01-01', '2000-01-02'])

        result = idx.insert(2, datetime(2000, 1, 5))
        exp = DatetimeIndex(['2000-01-04', '2000-01-01', '2000-01-05',
                             '2000-01-02'])
        self.assert_(result.equals(exp))

        idx = date_range('1/1/2000', periods=3, freq='M')
        result = idx.insert(3, datetime(2000, 4, 30))
        self.assert_(result.freqstr == 'M')

class TestLegacySupport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if py3compat.PY3:
            raise nose.SkipTest

        pth, _ = os.path.split(os.path.abspath(__file__))
        filepath = os.path.join(pth, 'data', 'frame.pickle')

        with open(filepath, 'rb') as f:
            cls.frame = pickle.load(f)

        filepath = os.path.join(pth, 'data', 'series.pickle')
        with open(filepath, 'rb') as f:
            cls.series = pickle.load(f)

    def test_pass_offset_warn(self):
        from StringIO import StringIO
        import sys
        buf = StringIO()

        sys.stderr = buf
        DatetimeIndex(start='1/1/2000', periods=10, offset='H')
        sys.stderr = sys.__stderr__

    def test_unpickle_legacy_frame(self):
        dtindex = DatetimeIndex(start='1/3/2005', end='1/14/2005',
                                freq=BDay(1))

        unpickled = self.frame

        self.assertEquals(type(unpickled.index), DatetimeIndex)
        self.assertEquals(len(unpickled), 10)
        self.assert_((unpickled.columns == Int64Index(np.arange(5))).all())
        self.assert_((unpickled.index == dtindex).all())
        self.assertEquals(unpickled.index.offset, BDay(1, normalize=True))

    def test_unpickle_legacy_series(self):
        from pandas.core.datetools import BDay

        unpickled = self.series

        dtindex = DatetimeIndex(start='1/3/2005', end='1/14/2005',
                                freq=BDay(1))

        self.assertEquals(type(unpickled.index), DatetimeIndex)
        self.assertEquals(len(unpickled), 10)
        self.assert_((unpickled.index == dtindex).all())
        self.assertEquals(unpickled.index.offset, BDay(1, normalize=True))

    def test_unpickle_legacy_len0_daterange(self):
        pth, _ = os.path.split(os.path.abspath(__file__))
        filepath = os.path.join(pth, 'data', 'series_daterange0.pickle')

        result = com.load(filepath)

        ex_index = DatetimeIndex([], freq='B')

        self.assert_(result.index.equals(ex_index))
        self.assert_(isinstance(result.index.freq, offsets.BDay))
        self.assert_(len(result) == 0)

    def test_arithmetic_interaction(self):
        index = self.frame.index
        obj_index = index.asobject

        dseries = Series(rand(len(index)), index=index)
        oseries = Series(dseries.values, index=obj_index)

        result = dseries + oseries
        expected = dseries * 2
        self.assert_(isinstance(result.index, DatetimeIndex))
        assert_series_equal(result, expected)

        result = dseries + oseries[:5]
        expected = dseries + dseries[:5]
        self.assert_(isinstance(result.index, DatetimeIndex))
        assert_series_equal(result, expected)

    def test_join_interaction(self):
        index = self.frame.index
        obj_index = index.asobject

        def _check_join(left, right, how='inner'):
            ra, rb, rc = left.join(right, how=how, return_indexers=True)
            ea, eb, ec = left.join(DatetimeIndex(right), how=how,
                                   return_indexers=True)

            self.assert_(isinstance(ra, DatetimeIndex))
            self.assert_(ra.equals(ea))

            assert_almost_equal(rb, eb)
            assert_almost_equal(rc, ec)

        _check_join(index[:15], obj_index[5:], how='inner')
        _check_join(index[:15], obj_index[5:], how='outer')
        _check_join(index[:15], obj_index[5:], how='right')
        _check_join(index[:15], obj_index[5:], how='left')

    def test_unpickle_daterange(self):
        pth, _ = os.path.split(os.path.abspath(__file__))
        filepath = os.path.join(pth, 'data', 'daterange_073.pickle')

        rng = com.load(filepath)
        self.assert_(type(rng[0]) == datetime)
        self.assert_(isinstance(rng.offset, offsets.BDay))
        self.assert_(rng.values.dtype == object)

    def test_setops(self):
        index = self.frame.index
        obj_index = index.asobject

        result = index[:5].union(obj_index[5:])
        expected = index
        self.assert_(isinstance(result, DatetimeIndex))
        self.assert_(result.equals(expected))

        result = index[:10].intersection(obj_index[5:])
        expected = index[5:10]
        self.assert_(isinstance(result, DatetimeIndex))
        self.assert_(result.equals(expected))

        result = index[:10] - obj_index[5:]
        expected = index[:5]
        self.assert_(isinstance(result, DatetimeIndex))
        self.assert_(result.equals(expected))

    def test_index_conversion(self):
        index = self.frame.index
        obj_index = index.asobject

        conv = DatetimeIndex(obj_index)
        self.assert_(conv.equals(index))

        self.assertRaises(ValueError, DatetimeIndex, ['a', 'b', 'c', 'd'])

    def test_tolist(self):
        rng = date_range('1/1/2000', periods=10)

        result = rng.tolist()
        self.assert_(isinstance(result[0], Timestamp))

    def test_object_convert_fail(self):
        idx = DatetimeIndex([NaT])
        self.assertRaises(ValueError, idx.astype, 'O')

    def test_setops_conversion_fail(self):
        index = self.frame.index

        right = Index(['a', 'b', 'c', 'd'])

        result = index.union(right)
        expected = Index(np.concatenate([index.asobject, right]))
        self.assert_(result.equals(expected))

        result = index.intersection(right)
        expected = Index([])
        self.assert_(result.equals(expected))

    def test_legacy_time_rules(self):
        rules = [('WEEKDAY', 'B'),
                 ('EOM', 'BM'),
                 ('W@MON', 'W-MON'), ('W@TUE', 'W-TUE'), ('W@WED', 'W-WED'),
                 ('W@THU', 'W-THU'), ('W@FRI', 'W-FRI'),
                 ('Q@JAN', 'BQ-JAN'), ('Q@FEB', 'BQ-FEB'), ('Q@MAR', 'BQ-MAR'),
                 ('A@JAN', 'BA-JAN'), ('A@FEB', 'BA-FEB'), ('A@MAR', 'BA-MAR'),
                 ('A@APR', 'BA-APR'), ('A@MAY', 'BA-MAY'), ('A@JUN', 'BA-JUN'),
                 ('A@JUL', 'BA-JUL'), ('A@AUG', 'BA-AUG'), ('A@SEP', 'BA-SEP'),
                 ('A@OCT', 'BA-OCT'), ('A@NOV', 'BA-NOV'), ('A@DEC', 'BA-DEC'),
                 ('WOM@1FRI', 'WOM-1FRI'), ('WOM@2FRI', 'WOM-2FRI'),
                 ('WOM@3FRI', 'WOM-3FRI'), ('WOM@4FRI', 'WOM-4FRI')]

        start, end = '1/1/2000', '1/1/2010'

        for old_freq, new_freq in rules:
            old_rng = date_range(start, end, freq=old_freq)
            new_rng = date_range(start, end, freq=new_freq)
            self.assert_(old_rng.equals(new_rng))

            # test get_legacy_offset_name
            offset = datetools.get_offset(new_freq)
            old_name = datetools.get_legacy_offset_name(offset)
            self.assertEquals(old_name, old_freq)

    def test_ms_vs_MS(self):
        left = datetools.get_offset('ms')
        right = datetools.get_offset('MS')
        self.assert_(left == datetools.Milli())
        self.assert_(right == datetools.MonthBegin())

    def test_rule_aliases(self):
        rule = datetools.to_offset('10us')
        self.assert_(rule == datetools.Micro(10))

    def test_slice_year(self):
        dti = DatetimeIndex(freq='B', start=datetime(2005,1,1), periods=500)

        s = Series(np.arange(len(dti)), index=dti)
        result = s['2005']
        expected = s[s.index.year == 2005]
        assert_series_equal(result, expected)

        df = DataFrame(np.random.rand(len(dti), 5), index=dti)
        result = df.ix['2005']
        expected = df[df.index.year == 2005]
        assert_frame_equal(result, expected)

        rng = date_range('1/1/2000', '1/1/2010')

        result = rng.get_loc('2009')
        expected = slice(3288, 3653)
        self.assert_(result == expected)

    def test_slice_quarter(self):
        dti = DatetimeIndex(freq='D', start=datetime(2000,6,1), periods=500)

        s = Series(np.arange(len(dti)), index=dti)
        self.assertEquals(len(s['2001Q1']), 90)

        df = DataFrame(np.random.rand(len(dti), 5), index=dti)
        self.assertEquals(len(df.ix['1Q01']), 90)

    def test_slice_month(self):
        dti = DatetimeIndex(freq='D', start=datetime(2005,1,1), periods=500)
        s = Series(np.arange(len(dti)), index=dti)
        self.assertEquals(len(s['2005-11']), 30)

        df = DataFrame(np.random.rand(len(dti), 5), index=dti)
        self.assertEquals(len(df.ix['2005-11']), 30)

    def test_partial_slice(self):
        rng = DatetimeIndex(freq='D', start=datetime(2005,1,1), periods=500)
        s = Series(np.arange(len(rng)), index=rng)

        result = s['2005-05':'2006-02']
        expected = s['20050501':'20060228']
        assert_series_equal(result, expected)

        result = s['2005-05':]
        expected = s['20050501':]
        assert_series_equal(result, expected)

        result = s[:'2006-02']
        expected = s[:'20060228']
        assert_series_equal(result, expected)

    def test_partial_not_monotonic(self):
        rng = date_range(datetime(2005,1,1), periods=20, freq='M')
        ts = Series(np.arange(len(rng)), index=rng)
        ts = ts.take(np.random.permutation(20))

        self.assertRaises(Exception, ts.__getitem__, '2005')

    def test_date_range_normalize(self):
        snap = datetime.today()
        n = 50

        rng = date_range(snap, periods=n, normalize=False, freq='2D')

        offset = timedelta(2)
        values = np.array([snap + i * offset for i in range(n)],
                          dtype='M8[ns]')

        self.assert_(np.array_equal(rng, values))

        rng = date_range('1/1/2000 08:15', periods=n, normalize=False, freq='B')
        the_time = time(8, 15)
        for val in rng:
            self.assert_(val.time() == the_time)

    def test_timedelta(self):
        # this is valid too
        index = date_range('1/1/2000', periods=50, freq='B')
        shifted = index + timedelta(1)
        back = shifted + timedelta(-1)
        self.assert_(tm.equalContents(index, back))
        self.assertEqual(shifted.freq, index.freq)
        self.assertEqual(shifted.freq, back.freq)

        result = index - timedelta(1)
        expected = index + timedelta(-1)
        self.assert_(result.equals(expected))

    def test_shift(self):
        ts = Series(np.random.randn(5),
                    index=date_range('1/1/2000', periods=5, freq='H'))

        result = ts.shift(1, freq='5T')
        exp_index = ts.index.shift(1, freq='5T')
        self.assert_(result.index.equals(exp_index))

        # GH #1063, multiple of same base
        result = ts.shift(1, freq='4H')
        exp_index = ts.index + datetools.Hour(4)
        self.assert_(result.index.equals(exp_index))

        idx = DatetimeIndex(['2000-01-01', '2000-01-02', '2000-01-04'])
        self.assertRaises(ValueError, idx.shift, 1)

    def test_setops_preserve_freq(self):
        rng = date_range('1/1/2000', '1/1/2002')

        result = rng[:50].union(rng[50:100])
        self.assert_(result.freq == rng.freq)

        result = rng[:50].union(rng[30:100])
        self.assert_(result.freq == rng.freq)

        result = rng[:50].union(rng[60:100])
        self.assert_(result.freq is None)

        result = rng[:50].intersection(rng[25:75])
        self.assert_(result.freqstr == 'D')

        nofreq = DatetimeIndex(list(rng[25:75]))
        result = rng[:50].union(nofreq)
        self.assert_(result.freq == rng.freq)

        result = rng[:50].intersection(nofreq)
        self.assert_(result.freq == rng.freq)


class TestLegacyCompat(unittest.TestCase):

    def setUp(self):
        from StringIO import StringIO
        # suppress deprecation warnings
        sys.stderr = StringIO()

    def test_inferTimeRule(self):
        from pandas.tseries.frequencies import inferTimeRule

        index1 = [datetime(2010, 1, 29, 0, 0),
                  datetime(2010, 2, 26, 0, 0),
                  datetime(2010, 3, 31, 0, 0)]

        index2 = [datetime(2010, 3, 26, 0, 0),
                  datetime(2010, 3, 29, 0, 0),
                  datetime(2010, 3, 30, 0, 0)]

        index3 = [datetime(2010, 3, 26, 0, 0),
                  datetime(2010, 3, 27, 0, 0),
                  datetime(2010, 3, 29, 0, 0)]

        # LEGACY
        assert inferTimeRule(index1) == 'EOM'
        assert inferTimeRule(index2) == 'WEEKDAY'

        self.assertRaises(Exception, inferTimeRule, index1[:2])
        self.assertRaises(Exception, inferTimeRule, index3)

    def test_time_rule(self):
        result = DateRange('1/1/2000', '1/30/2000', time_rule='WEEKDAY')
        result2 = DateRange('1/1/2000', '1/30/2000', timeRule='WEEKDAY')
        expected = date_range('1/1/2000', '1/30/2000', freq='B')

        self.assert_(result.equals(expected))
        self.assert_(result2.equals(expected))

    def tearDown(self):
        sys.stderr = sys.__stderr__


class TestDatetime64(unittest.TestCase):
    """
    Also test supoprt for datetime64[ns] in Series / DataFrame
    """


    def setUp(self):
        dti = DatetimeIndex(start=datetime(2005,1,1),
                            end=datetime(2005,1,10), freq='Min')
        self.series = Series(rand(len(dti)), dti)

    def test_datetimeindex_accessors(self):
        dti = DatetimeIndex(freq='Q-JAN', start=datetime(1997,12,31), periods=100)

        self.assertEquals(dti.year[0], 1998)
        self.assertEquals(dti.month[0], 1)
        self.assertEquals(dti.day[0], 31)
        self.assertEquals(dti.hour[0], 0)
        self.assertEquals(dti.minute[0], 0)
        self.assertEquals(dti.second[0], 0)
        self.assertEquals(dti.microsecond[0], 0)
        self.assertEquals(dti.dayofweek[0], 5)

        self.assertEquals(dti.dayofyear[0], 31)
        self.assertEquals(dti.dayofyear[1], 120)

        self.assertEquals(dti.weekofyear[0], 5)
        self.assertEquals(dti.weekofyear[1], 18)

        self.assertEquals(dti.quarter[0], 1)
        self.assertEquals(dti.quarter[1], 2)

        self.assertEquals(len(dti.year), 100)
        self.assertEquals(len(dti.month), 100)
        self.assertEquals(len(dti.day), 100)
        self.assertEquals(len(dti.hour), 100)
        self.assertEquals(len(dti.minute), 100)
        self.assertEquals(len(dti.second), 100)
        self.assertEquals(len(dti.microsecond), 100)
        self.assertEquals(len(dti.dayofweek), 100)
        self.assertEquals(len(dti.dayofyear), 100)
        self.assertEquals(len(dti.weekofyear), 100)
        self.assertEquals(len(dti.quarter), 100)

    def test_nanosecond_field(self):
        dti = DatetimeIndex(np.arange(10))

        self.assert_(np.array_equal(dti.nanosecond, np.arange(10)))

    def test_datetimeindex_diff(self):
        dti1 = DatetimeIndex(freq='Q-JAN', start=datetime(1997,12,31),
                             periods=100)
        dti2 = DatetimeIndex(freq='Q-JAN', start=datetime(1997,12,31),
                             periods=98)
        self.assert_( len(dti1.diff(dti2)) == 2)

    def test_fancy_getitem(self):
        dti = DatetimeIndex(freq='WOM-1FRI', start=datetime(2005,1,1),
                            end=datetime(2010,1,1))

        s = Series(np.arange(len(dti)), index=dti)

        self.assertEquals(s[48], 48)
        self.assertEquals(s['1/2/2009'], 48)
        self.assertEquals(s['2009-1-2'], 48)
        self.assertEquals(s[datetime(2009,1,2)], 48)
        self.assertEquals(s[lib.Timestamp(datetime(2009,1,2))], 48)
        self.assertRaises(KeyError, s.__getitem__, '2009-1-3')

        assert_series_equal(s['3/6/2009':'2009-06-05'],
                            s[datetime(2009,3,6):datetime(2009,6,5)])

    def test_fancy_setitem(self):
        dti = DatetimeIndex(freq='WOM-1FRI', start=datetime(2005,1,1),
                            end=datetime(2010,1,1))

        s = Series(np.arange(len(dti)), index=dti)
        s[48] = -1
        self.assertEquals(s[48], -1)
        s['1/2/2009'] = -2
        self.assertEquals(s[48], -2)
        s['1/2/2009':'2009-06-05'] = -3
        self.assert_((s[48:54] == -3).all())

    def test_datetimeindex_constructor(self):
        arr = ['1/1/2005', '1/2/2005', 'Jn 3, 2005', '2005-01-04']
        self.assertRaises(Exception, DatetimeIndex, arr)

        arr = ['1/1/2005', '1/2/2005', '1/3/2005', '2005-01-04']
        idx1 = DatetimeIndex(arr)

        arr = [datetime(2005,1,1), '1/2/2005', '1/3/2005', '2005-01-04']
        idx2 = DatetimeIndex(arr)

        arr = [lib.Timestamp(datetime(2005,1,1)), '1/2/2005', '1/3/2005',
               '2005-01-04']
        idx3 = DatetimeIndex(arr)

        arr = np.array(['1/1/2005', '1/2/2005', '1/3/2005',
                        '2005-01-04'], dtype='O')
        idx4 = DatetimeIndex(arr)

        arr = to_datetime(['1/1/2005', '1/2/2005', '1/3/2005', '2005-01-04'])
        idx5 = DatetimeIndex(arr)

        arr = to_datetime(['1/1/2005', '1/2/2005', 'Jan 3, 2005', '2005-01-04'])
        idx6 = DatetimeIndex(arr)

        for other in [idx2, idx3, idx4, idx5, idx6]:
            self.assert_( (idx1.values == other.values).all() )

        sdate = datetime(1999, 12, 25)
        edate = datetime(2000, 1, 1)
        idx = DatetimeIndex(start=sdate, freq='1B', periods=20)
        self.assertEquals(len(idx), 20)
        self.assertEquals(idx[0], sdate + 0 * dt.bday)
        self.assertEquals(idx.freq, 'B')

        idx = DatetimeIndex(end=edate, freq=('D', 5), periods=20)
        self.assertEquals(len(idx), 20)
        self.assertEquals(idx[-1], edate)
        self.assertEquals(idx.freq, '5D')

        idx1 = DatetimeIndex(start=sdate, end=edate, freq='W-SUN')
        idx2 = DatetimeIndex(start=sdate, end=edate,
                             freq=dt.Week(weekday=6))
        self.assertEquals(len(idx1), len(idx2))
        self.assertEquals(idx1.offset, idx2.offset)

    def test_dti_snap(self):
        dti = DatetimeIndex(['1/1/2002', '1/2/2002', '1/3/2002', '1/4/2002',
                             '1/5/2002', '1/6/2002', '1/7/2002'], freq='D')

        res = dti.snap(freq='W-MON')
        exp = date_range('12/31/2001', '1/7/2002', freq='w-mon')
        exp = exp.repeat([3, 4])
        self.assert_( (res == exp).all() )

        res = dti.snap(freq='B')

        exp = date_range('1/1/2002', '1/7/2002', freq='b')
        exp = exp.repeat([1, 1, 1, 2, 2])
        self.assert_( (res == exp).all() )

    def test_dti_reset_index_round_trip(self):
        dti = DatetimeIndex(start='1/1/2001', end='6/1/2001', freq='D')
        d1 = DataFrame({'v' : np.random.rand(len(dti))}, index=dti)
        d2 = d1.reset_index()
        self.assert_(d2.dtypes[0] == np.dtype('M8[ns]'))
        d3 = d2.set_index('index')
        assert_frame_equal(d1, d3)

    def test_datetimeindex_union_join_empty(self):
        dti = DatetimeIndex(start='1/1/2001', end='2/1/2001', freq='D')
        empty = Index([])

        result = dti.union(empty)
        self.assert_(isinstance(result, DatetimeIndex))
        self.assert_(result is result)

        result = dti.join(empty)
        self.assert_(isinstance(result, DatetimeIndex))

    # TODO: test merge & concat with datetime64 block


class TestSeriesDatetime64(unittest.TestCase):

    def setUp(self):
        self.series = Series(date_range('1/1/2000', periods=10))

    def test_auto_conversion(self):
        series = Series(list(date_range('1/1/2000', periods=10)))
        self.assert_(series.dtype == object)

    def test_constructor_cant_cast_datetime64(self):
        self.assertRaises(TypeError, Series,
                          date_range('1/1/2000', periods=10), dtype=float)

    def test_series_comparison_scalars(self):
        val = datetime(2000, 1, 4)
        result = self.series > val
        expected = np.array([x > val for x in self.series])
        self.assert_(np.array_equal(result, expected))

        val = self.series[5]
        result = self.series > val
        expected = np.array([x > val for x in self.series])
        self.assert_(np.array_equal(result, expected))

    def test_between(self):
        left, right = self.series[[2, 7]]

        result = self.series.between(left, right)
        expected = (self.series >= left) & (self.series <= right)
        assert_series_equal(result, expected)

    #----------------------------------------------------------------------
    # NaT support

    def test_NaT_scalar(self):
        series = Series([0, 1000, 2000, iNaT], dtype='M8[ns]')

        val = series[3]
        self.assert_(com.isnull(val))

        series[2] = val
        self.assert_(com.isnull(series[2]))

    def test_set_none_nan(self):
        self.series[3] = None
        self.assert_(self.series[3] is lib.NaT)

        self.series[3:5] = None
        self.assert_(self.series[4] is lib.NaT)

        self.series[5] = np.nan
        self.assert_(self.series[5] is lib.NaT)

        self.series[5:7] = np.nan
        self.assert_(self.series[6] is lib.NaT)

    def test_intercept_astype_object(self):
        # Work around NumPy 1.6 bugs
        result = self.series.astype(object)
        result2 = self.series.astype('O')
        expected = Series([x for x in self.series], dtype=object)

        assert_series_equal(result, expected)
        assert_series_equal(result2, expected)

        df = DataFrame({'a': self.series,
                        'b' : np.random.randn(len(self.series))})

        result = df.values.squeeze()
        self.assert_((result[:, 0] == expected.values).all())

        df = DataFrame({'a': self.series,
                        'b' : ['foo'] * len(self.series)})

        result = df.values.squeeze()
        self.assert_((result[:, 0] == expected.values).all())

    def test_union(self):
        rng1 = date_range('1/1/1999', '1/1/2012', freq='MS')
        s1 = Series(np.random.randn(len(rng1)), rng1)

        rng2 = date_range('1/1/1980', '12/1/2001', freq='MS')
        s2 = Series(np.random.randn(len(rng2)), rng2)
        df = DataFrame({'s1' : s1, 's2' : s2})
        self.assert_(df.index.values.dtype == np.dtype('M8[ns]'))


class TestTimestamp(unittest.TestCase):

    def test_basics_nanos(self):
        val = np.int64(946684800000000000).view('M8[ns]')
        stamp = Timestamp(val.view('i8') + 500)
        self.assert_(stamp.year == 2000)
        self.assert_(stamp.month == 1)
        self.assert_(stamp.microsecond == 0)
        self.assert_(stamp.nanosecond == 500)

    def test_comparison(self):
        # 5-18-2012 00:00:00.000
        stamp = 1337299200000000000L

        val = Timestamp(stamp)

        self.assert_(val == val)
        self.assert_(not val != val)
        self.assert_(not val < val)
        self.assert_(val <= val)
        self.assert_(not val > val)
        self.assert_(val >= val)

        other = datetime(2012, 5, 18)
        self.assert_(val == other)
        self.assert_(not val != other)
        self.assert_(not val < other)
        self.assert_(val <= other)
        self.assert_(not val > other)
        self.assert_(val >= other)

        other = Timestamp(stamp + 100)

        self.assert_(not val == other)
        self.assert_(val != other)
        self.assert_(val < other)
        self.assert_(val <= other)
        self.assert_(other > val)
        self.assert_(other >= val)

    def test_cant_compare_tz_naive_w_aware(self):
        _skip_if_no_pytz()
        # #1404
        a = Timestamp('3/12/2012')
        b = Timestamp('3/12/2012', tz='utc')

        self.assertRaises(Exception, a.__eq__, b)
        self.assertRaises(Exception, a.__ne__, b)
        self.assertRaises(Exception, a.__lt__, b)
        self.assertRaises(Exception, a.__gt__, b)
        self.assertRaises(Exception, b.__eq__, a)
        self.assertRaises(Exception, b.__ne__, a)
        self.assertRaises(Exception, b.__lt__, a)
        self.assertRaises(Exception, b.__gt__, a)

        self.assertRaises(Exception, a.__eq__, b.to_pydatetime())
        self.assertRaises(Exception, a.to_pydatetime().__eq__, b)

    def test_delta_preserve_nanos(self):
        val = Timestamp(1337299200000000123L)
        result = val + timedelta(1)
        self.assert_(result.nanosecond == val.nanosecond)

    def test_frequency_misc(self):
        self.assertEquals(fmod.get_freq_group('T'),
                          fmod.FreqGroup.FR_MIN)

        code, stride = fmod.get_freq_code(offsets.Hour())
        self.assertEquals(code, fmod.FreqGroup.FR_HR)

        code, stride = fmod.get_freq_code((5, 'T'))
        self.assertEquals(code, fmod.FreqGroup.FR_MIN)
        self.assertEquals(stride, 5)

        offset = offsets.Hour()
        result = fmod.to_offset(offset)
        self.assertEquals(result, offset)

        result = fmod.to_offset((5, 'T'))
        expected = offsets.Minute(5)
        self.assertEquals(result, expected)

        self.assertRaises(KeyError, fmod.get_freq_code, (5, 'baz'))

        self.assertRaises(ValueError, fmod.to_offset, '100foo')

        self.assertRaises(ValueError, fmod.to_offset, ('', ''))

        result = fmod.get_standard_freq(offsets.Hour())
        self.assertEquals(result, 'H')

    def test_hash_equivalent(self):
        d = {datetime(2011, 1, 1) : 5}
        stamp = Timestamp(datetime(2011, 1, 1))
        self.assertEquals(d[stamp], 5)

if __name__ == '__main__':
    nose.runmodule(argv=[__file__,'-vvs','-x','--pdb', '--pdb-failure'],
                   exit=False)
