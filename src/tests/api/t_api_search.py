#!/usr/bin/python
#
# CDDL HEADER START
#
# The contents of this file are subject to the terms of the
# Common Development and Distribution License (the "License").
# You may not use this file except in compliance with the License.
#
# You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
# or http://www.opensolaris.org/os/licensing.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# When distributing Covered Code, include this CDDL HEADER in each
# file and include the License file at usr/src/OPENSOLARIS.LICENSE.
# If applicable, add the following below this CDDL HEADER, with the
# fields enclosed by brackets "[]" replaced with your own identifying
# information: Portions Copyright [yyyy] [name of copyright owner]
#
# CDDL HEADER END
#

# Copyright 2010 Sun Microsystems, Inc.  All rights reserved.
# Use is subject to license terms.

import testutils
if __name__ == "__main__":
	testutils.setup_environment("../../../proto")
import pkg5unittest

import copy
import difflib
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import urllib2

import pkg.client.api as api
import pkg.client.api_errors as api_errors
import pkg.client.query_parser as query_parser
import pkg.client.progress as progress
import pkg.fmri as fmri
import pkg.indexer as indexer
import pkg.portable as portable
import pkg.search_storage as ss
import pkg.server.repository as srepo

API_VERSION = 36
PKG_CLIENT_NAME = "pkg"

class TestApiSearchBasics(pkg5unittest.SingleDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            add dir mode=0755 owner=root group=bin path=/usr/lib/python2.6/vendor-packages/OpenSSL
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path
            add set name=com.sun.service.incorporated_changes value="6556919 6627937"
            add set name=com.sun.service.random_test value=42 value=79
            add set name=com.sun.service.bug_ids value=4641790 value=4725245 value=4817791 value=4851433 value=4897491 value=4913776 value=6178339 value=6556919 value=6627937
            add set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"
            add set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z
            add set name=description value='FOOO bAr O OO OOO' value="whee fun"
            add set name='weirdness' value='] [ * ?'
            add signature pkg.sig_bit1=sig_bit_val1 pkg.sig_bit2=sig_bit_val2
            add set name=smf.fmri value=svc:/milestone/multi-user-server:default
            close """

        example_pkg11 = """
            open example_pkg@1.1,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin
            add file tmp/example_file mode=0555 owner=root group=bin path=/bin/example_path11
            close """

        incorp_pkg10 = """
            open incorp_pkg@1.0,5.11-0
            add depend fmri=example_pkg@1.0,5.11-0 type=incorporate
            close """

        incorp_pkg11 = """
            open incorp_pkg@1.1,5.11-0
            add depend fmri=example_pkg@1.1,5.11-0 type=incorporate
            close """

        another_pkg10 = """
            open another_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bazbin
            close """

        bad_pkg10 = """
            open bad_pkg@1.0,5.11-0
            add dir path=badfoo/ mode=0755 owner=root group=bin
            close """

        space_pkg10 = """
            open space_pkg@1.0,5.11-0
            add file tmp/example_file mode=0444 owner=nobody group=sys path='unique/with a space'
            add dir mode=0755 owner=root group=bin path=unique_dir
            close """

        cat_pkg10 = """
            open cat@1.0,5.11-0
            add set name=info.classification value=org.opensolaris.category.2008:System/Security value=org.random:Other/Category
            close """

        cat2_pkg10 = """
            open cat2@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video" value=Developer/C
            close """

        cat3_pkg10 = """
            open cat3@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:foo/bar/baz/bill/beam/asda"
            close """

        bad_cat_pkg10 = """
            open badcat@1.0,5.11-0
            add set name=info.classification value="TestBad1/TestBad2"
            close """

        bad_cat2_pkg10 = """
            open badcat2@1.0,5.11-0
            add set name=info.classification value="org.opensolaris.category.2008:TestBad1:TestBad2"
            close """

        fat_pkg10 = """
open fat@1.0,5.11-0
add set name=variant.arch value=sparc value=i386
add set name=description value="i386 variant" variant.arch=i386
add set name=description value="sparc variant" variant.arch=sparc
close """

        bogus_pkg10 = """
set name=pkg.fmri value=pkg:/bogus_pkg@1.0,5.11-0:20090326T233451Z
set name=description value=""validation with simple chains of constraints ""
set name=pkg.description value="pseudo-hashes as arrays tied to a "type" (list of fields)"
depend fmri=XML-Atom-Entry
set name=com.sun.service.incorporated_changes value="6556919 6627937"
"""
        bogus_fmri = fmri.PkgFmri("bogus_pkg@1.0,5.11-0:20090326T233451Z")

        hierarchical_named_pkg = """
open pa/pb/pc/pfoo@1.0,5.11-0
close """

        bug_8492_manf_1 = """
open b1@1.0,5.11-0
add set description="Image Packaging System"
close """

        bug_8492_manf_2 = """
open b2@1.0,5.11-0
add set description="Image Packaging System"
close """

        res_8492_1 = set([('pkg:/b1@1.0-0', 'Image Packaging System', 'set name=description value="Image Packaging System"')])
        res_8492_2 = set([('pkg:/b2@1.0-0', 'Image Packaging System', 'set name=description value="Image Packaging System"')])
        
        remote_fmri_string = ('pkg:/example_pkg@1.0-0', 'test/example_pkg',
            'set name=pkg.fmri value=pkg://test/example_pkg@1.0,5.11-0:')

        res_remote_pkg = set([
            remote_fmri_string
        ])

        res_remote_path = set([
            ("pkg:/example_pkg@1.0-0", "basename","file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12")
        ])

        res_remote_path_of_example_path = set([
            ("pkg:/example_pkg@1.0-0", "path","file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12")
        ])

        res_remote_bin = set([
            ("pkg:/example_pkg@1.0-0", "path", "dir group=bin mode=0755 owner=root path=bin")
        ])

        res_remote_openssl = set([
            ("pkg:/example_pkg@1.0-0", "basename", "dir group=bin mode=0755 owner=root path=usr/lib/python2.6/vendor-packages/OpenSSL")
        ])

        res_remote_bug_id = set([
            ("pkg:/example_pkg@1.0-0", "4851433", 'set name=com.sun.service.bug_ids value=4641790 value=4725245 value=4817791 value=4851433 value=4897491 value=4913776 value=6178339 value=6556919 value=6627937')
        ])

        res_remote_bug_id_4725245 = set([
            ("pkg:/example_pkg@1.0-0", "4725245", 'set name=com.sun.service.bug_ids value=4641790 value=4725245 value=4817791 value=4851433 value=4897491 value=4913776 value=6178339 value=6556919 value=6627937')
        ])


        res_remote_inc_changes = set([
            ("pkg:/example_pkg@1.0-0", "6556919 6627937", 'set name=com.sun.service.incorporated_changes value="6556919 6627937"'),
            ("pkg:/example_pkg@1.0-0", "6556919", 'set name=com.sun.service.bug_ids value=4641790 value=4725245 value=4817791 value=4851433 value=4897491 value=4913776 value=6178339 value=6556919 value=6627937')
        ])

        res_remote_random_test = set([
            ("pkg:/example_pkg@1.0-0", "42", "set name=com.sun.service.random_test value=42 value=79")
        ])

        res_remote_random_test_79 = set([
            ("pkg:/example_pkg@1.0-0", "79", "set name=com.sun.service.random_test value=42 value=79")
        ])

        res_remote_keywords = set([
            ("pkg:/example_pkg@1.0-0", "sort null -n -m -t sort 0x86 separator", 'set name=com.sun.service.keywords value="sort null -n -m -t sort 0x86 separator"')
        ])

        res_remote_wildcard = res_remote_path.union(set([
            remote_fmri_string,
            ('pkg:/example_pkg@1.0-0', 'basename', 'dir group=bin mode=0755 owner=root path=bin/example_dir')
        ]))

        res_remote_glob = set([
            remote_fmri_string,
            ('pkg:/example_pkg@1.0-0', 'path', 'dir group=bin mode=0755 owner=root path=bin/example_dir'),
            ('pkg:/example_pkg@1.0-0', 'basename', 'dir group=bin mode=0755 owner=root path=bin/example_dir'),
            ('pkg:/example_pkg@1.0-0', 'path', 'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12')
        ]) | res_remote_path

        res_remote_foo = set([
            ('pkg:/example_pkg@1.0-0', 'FOOO bAr O OO OOO', 'set name=description value="FOOO bAr O OO OOO" value="whee fun"')
        ])

        res_remote_weird = set([
            ('pkg:/example_pkg@1.0-0', '] [ * ?', 'set name=weirdness value="] [ * ?"')
        ])

        local_fmri_string = ('pkg:/example_pkg@1.0-0', 'test/example_pkg',
            'set name=pkg.fmri value=pkg://test/example_pkg@1.0,5.11-0:')

        res_local_pkg = set([
                local_fmri_string
                ])

        res_local_path = copy.copy(res_remote_path)

        res_local_bin = copy.copy(res_remote_bin)

        res_local_bug_id = copy.copy(res_remote_bug_id)

        res_local_inc_changes = copy.copy(res_remote_inc_changes)

        res_local_random_test = copy.copy(res_remote_random_test)

        res_local_keywords = copy.copy(res_remote_keywords)

        res_local_wildcard = copy.copy(res_remote_wildcard)
        res_local_wildcard.add(local_fmri_string)

        res_local_glob = copy.copy(res_remote_glob)
        res_local_glob.add(local_fmri_string)

        res_local_foo = copy.copy(res_remote_foo)

        res_local_openssl = copy.copy(res_remote_openssl)

        res_local_path_example11 = set([
            ("pkg:/example_pkg@1.1-0", "basename", "file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path11 pkg.csize=30 pkg.size=12")
        ])

        res_local_bin_example11 = set([
            ("pkg:/example_pkg@1.1-0", "path", "dir group=bin mode=0755 owner=root path=bin")
        ])

        res_local_pkg_example11 = set([
            ("pkg:/example_pkg@1.1-0", "test/example_pkg", "set name=pkg.fmri value=pkg://test/example_pkg@1.1,5.11-0:")
        ])

        res_local_wildcard_example11 = set([
            ("pkg:/example_pkg@1.1-0", "basename", "file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path11 pkg.csize=30 pkg.size=12"),
        ]).union(res_local_pkg_example11)

        res_cat_pkg10 = set([
            ('pkg:/cat@1.0-0', 'System/Security', 'set name=info.classification value=org.opensolaris.category.2008:System/Security value=org.random:Other/Category')
        ])

        res_cat_pkg10_2 = set([
            ('pkg:/cat@1.0-0', 'Other/Category', 'set name=info.classification value=org.opensolaris.category.2008:System/Security value=org.random:Other/Category')
        ])

        res_cat2_pkg10 = set([
            ('pkg:/cat2@1.0-0', 'Applications/Sound and Video', 'set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video" value=Developer/C')
        ])

        res_cat2_pkg10_2 = set([
            ('pkg:/cat2@1.0-0', 'Developer/C', 'set name=info.classification value="org.opensolaris.category.2008:Applications/Sound and Video" value=Developer/C')
        ])

        res_cat3_pkg10 = set([
            ('pkg:/cat3@1.0-0', 'foo/bar/baz/bill/beam/asda', 'set name=info.classification value=org.opensolaris.category.2008:foo/bar/baz/bill/beam/asda')
        ])

        res_fat10_i386 = set([
            ('pkg:/fat@1.0-0', 'i386 variant', 'set name=description value="i386 variant" variant.arch=i386'),
            ('pkg:/fat@1.0-0', 'i386 variant', 'set name=description value="i386 variant" variant.arch=i386'),
            ('pkg:/fat@1.0-0', 'i386', 'set name=variant.arch value=sparc value=i386'),
        ])

        res_fat10_sparc = set([
            ('pkg:/fat@1.0-0', 'sparc variant', 'set name=description value="sparc variant" variant.arch=sparc'),
            ('pkg:/fat@1.0-0', 'sparc', 'set name=variant.arch value=sparc value=i386')
        ])

        fat_10_fmri_string = set([('pkg:/fat@1.0-0', 'test/fat', 'set name=pkg.fmri value=pkg://test/fat@1.0,5.11-0:')])

        res_remote_fat10_star = fat_10_fmri_string | res_fat10_sparc | res_fat10_i386

        res_local_fat10_i386_star = res_fat10_i386.union(set([
            ('pkg:/fat@1.0-0', 'sparc', 'set name=variant.arch value=sparc value=i386')
        ])).union(fat_10_fmri_string)

        res_local_fat10_sparc_star = res_fat10_sparc.union(set([
            ('pkg:/fat@1.0-0', 'i386', 'set name=variant.arch value=sparc value=i386')
        ])).union(fat_10_fmri_string)

        res_space_with_star = set([
            ('pkg:/space_pkg@1.0-0', 'basename', 'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=sys mode=0444 owner=nobody path="unique/with a space" pkg.csize=30 pkg.size=12')
        ])

        res_space_space_star = set([
            ('pkg:/space_pkg@1.0-0', 'basename', 'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=sys mode=0444 owner=nobody path="unique/with a space" pkg.csize=30 pkg.size=12'), ('pkg:/space_pkg@1.0-0', 'path', 'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=sys mode=0444 owner=nobody path="unique/with a space" pkg.csize=30 pkg.size=12')
        ])

        res_space_unique = set([
            ('pkg:/space_pkg@1.0-0', 'basename', 'dir group=bin mode=0755 owner=root path=unique_dir')
        ])

        # This is a copy of the 3.81%2C5.11-0.89%3A20080527T163123Z version of
        # SUNWgmake from ipkg with the file and liscense actions changed so
        # that they all take /tmp/example file when sending.
        bug_983_manifest = """
open SUNWgmake@3.81,5.11-0.89
add dir group=sys mode=0755 owner=root path=usr
add dir group=bin mode=0755 owner=root path=usr/bin
add dir group=bin mode=0755 owner=root path=usr/gnu
add dir group=bin mode=0755 owner=root path=usr/gnu/bin
add link path=usr/gnu/bin/make target=../../bin/gmake
add dir group=sys mode=0755 owner=root path=usr/gnu/share
add dir group=bin mode=0755 owner=root path=usr/gnu/share/man
add dir group=bin mode=0755 owner=root path=usr/gnu/share/man/man1
add link path=usr/gnu/share/man/man1/make.1 target=../../../../share/man/man1/gmake.1
add dir group=bin mode=0755 owner=root path=usr/sfw
add dir group=bin mode=0755 owner=root path=usr/sfw/bin
add link path=usr/sfw/bin/gmake target=../../bin/gmake
add dir group=bin mode=0755 owner=root path=usr/sfw/share
add dir group=bin mode=0755 owner=root path=usr/sfw/share/man
add dir group=bin mode=0755 owner=root path=usr/sfw/share/man/man1
add link path=usr/sfw/share/man/man1/gmake.1 target=../../../../share/man/man1/gmake.1
add dir group=sys mode=0755 owner=root path=usr/share
add dir group=bin mode=0755 owner=root path=usr/share/info
add dir group=bin mode=0755 owner=root path=usr/share/man
add dir group=bin mode=0755 owner=root path=usr/share/man/man1
add file tmp/example_file elfarch=i386 elfbits=32 elfhash=68cca393e816e6adcbac1e8ffe9c618de70413e0 group=bin mode=0555 owner=root path=usr/bin/gmake pkg.size=12
add file tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info pkg.size=12
add file tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-1 pkg.size=12
add file tmp/example_file group=bin mode=0444 owner=root path=usr/share/info/make.info-2 pkg.size=12
add file tmp/example_file group=bin mode=0444 owner=root path=usr/share/man/man1/gmake.1 pkg.size=12
add license tmp/example_file license=SUNWgmake.copyright pkg.size=12 transaction_id=1211931083_pkg%3A%2FSUNWgmake%403.81%2C5.11-0.89%3A20080527T163123Z
add depend fmri=pkg:/SUNWcsl@0.5.11-0.89 type=require
add depend fmri=SUNWtestbar@0.5.11-0.111 type=require
add depend fmri=SUNWtestfoo@0.5.11-0.111 type=incorporate
add set name=description value="gmake - GNU make"
add legacy arch=i386 category=system desc="GNU make - A utility used to build software (gmake) 3.81" hotline="Please contact your local service provider" name="gmake - GNU make" pkg=SUNWgmake vendor="Sun Microsystems, Inc." version=11.11.0,REV=2008.04.29.02.08
close
"""

        res_bug_983 = set([
            ("pkg:/SUNWgmake@3.81-0.89", "basename", "link path=usr/sfw/bin/gmake target=../../bin/gmake"),
            ('pkg:/SUNWgmake@3.81-0.89', 'basename', 'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 elfarch=i386 elfbits=32 elfhash=68cca393e816e6adcbac1e8ffe9c618de70413e0 group=bin mode=0555 owner=root path=usr/bin/gmake pkg.csize=30 pkg.size=12'),
            ('pkg:/SUNWgmake@3.81-0.89', 'gmake - GNU make', 'set name=description value="gmake - GNU make"')
        ])

        res_983_csl_dependency = set([
            ('pkg:/SUNWgmake@3.81-0.89', 'require', 'depend fmri=pkg:/SUNWcsl@0.5.11-0.89 type=require')
        ])

        res_983_bar_dependency = set([
            ('pkg:/SUNWgmake@3.81-0.89', 'require', 'depend fmri=SUNWtestbar@0.5.11-0.111 type=require')
        ])

        res_983_foo_dependency = set([
            ('pkg:/SUNWgmake@3.81-0.89', 'incorporate', 'depend fmri=SUNWtestfoo@0.5.11-0.111 type=incorporate')
        ])

        res_local_pkg_ret_pkg = set([
            "pkg:/example_pkg@1.0-0"
        ])

        res_remote_pkg_ret_pkg = set([
            "pkg:/example_pkg@1.0-0"
        ])

        res_remote_file = set([
            ('pkg:/example_pkg@1.0-0',
             'path',
             'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12'),
            ('pkg:/example_pkg@1.0-0',
             'a686473102ba73bd7920fc0ab1d97e00a24ed704',
             'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12')
        ]) | res_remote_path

        res_remote_url = set([
            ('pkg:/example_pkg@1.0-0',
            'http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z',
            'set name=com.sun.service.info_url value=http://service.opensolaris.com/xml/pkg/SUNWcsu@0.5.11,5.11-1:20080514I120000Z'),
        ])

        res_remote_path_extra = set([
            ('pkg:/example_pkg@1.0-0',
             'basename',
             'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12'),
            ('pkg:/example_pkg@1.0-0',
             'path',
             'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12'),
            ('pkg:/example_pkg@1.0-0',
             'a686473102ba73bd7920fc0ab1d97e00a24ed704',
             'file a686473102ba73bd7920fc0ab1d97e00a24ed704 chash=f88920ce1f61db185d127ccb32dc8cf401ae7a83 group=bin mode=0555 owner=root path=bin/example_path pkg.csize=30 pkg.size=12')
        ])

        res_bad_pkg = set([
            ('pkg:/bad_pkg@1.0-0', 'basename',
             'dir group=bin mode=0755 owner=root path=badfoo/')
        ])

        hierarchical_named_pkg_res = set([
            ("pkg:/pa/pb/pc/pfoo@1.0-0", "test/pa/pb/pc/pfoo", "set name=pkg.fmri value=pkg://test/pa/pb/pc/pfoo@1.0,5.11-0:")
        ])

        fast_add_after_install = set([
            "VERSION: 2\n",
            "pkg22@1.0,5.11",
            "pkg21@1.0,5.11"
        ])

        fast_remove_after_install = set([
            "VERSION: 2\n",
        ])

        fast_add_after_first_update = set([
            "VERSION: 2\n",
            "pkg0@2.0,5.11",
            "pkg22@1.0,5.11",
            "pkg21@1.0,5.11",
            "pkg1@2.0,5.11"
        ])

        fast_remove_after_first_update = set([
            "VERSION: 2\n",
            "pkg0@1.0,5.11",
            "pkg1@1.0,5.11"
        ])

        res_smf_svc = set([
            ('pkg:/example_pkg@1.0-0',
            'svc:/milestone/multi-user-server:default',
            'set name=smf.fmri value=svc:/milestone/multi-user-server:default')
        ])

        fast_add_after_second_update = set(["VERSION: 2\n"])

        fast_remove_after_second_update = set(["VERSION: 2\n"])

        debug_features = []

        # We wire the contents of the example file to a well known string
        # so that the hash is also well known.
        misc_files = { "tmp/example_file" : "magic banana" }

        def setUp(self):
                pkg5unittest.SingleDepotTestCase.setUp(self,
                    debug_features=self.debug_features)
                self.testdata_dir = os.path.join(self.test_root,
                    "search_results")
                os.mkdir(self.testdata_dir)
                self._dir_restore_functions = [self._restore_dir,
                    self._restore_dir_preserve_hash]
                self.make_misc_files(self.misc_files)

        def _check(self, proposed_answer, correct_answer):
                if correct_answer == proposed_answer:
                        return True
                else:
                        self.debug("Proposed Answer: " + str(proposed_answer))
                        self.debug("Correct Answer : " + str(correct_answer))
                        if isinstance(correct_answer, set) and \
                            isinstance(proposed_answer, set):
                                self.debug("Missing: " +
                                    str(correct_answer - proposed_answer))
                                self.debug("Extra  : " +
                                    str(proposed_answer - correct_answer))
                        self.assertEqual(correct_answer, proposed_answer)

        @staticmethod
        def _replace_act(act):
                if act.startswith('set name=pkg.fmri'):
                        return act.strip().rsplit(":", 1)[0] + ":"
                else:
                        return act.strip()

        @staticmethod
        def _extract_action_from_res(it):
                return (
                    (fmri.PkgFmri(str(pkg_name)).get_short_fmri(), piece,
                    TestApiSearchBasics._replace_act(act))
                    for query_num, auth, (version, return_type,
                    (pkg_name, piece, act))
                    in it
                )

        @staticmethod
        def _extract_package_from_res(it):
                return (
                    (fmri.PkgFmri(str(pkg_name)).get_short_fmri())
                    for query_num, auth, (version, return_type, pkg_name)
                    in it
                )

        @staticmethod
        def _get_lines(fp):
                fh = open(fp, "rb")
                lines = fh.readlines()
                fh.close()
                return lines

        def _search_op(self, api_obj, remote, token, test_value,
            case_sensitive=False, return_actions=True, num_to_return=None,
            start_point=None, servers=None, prune_versions=True):
                query = [api.Query(token, case_sensitive, return_actions,
                    num_to_return, start_point)]
                self._search_op_common(api_obj, remote, query, test_value,
                    return_actions, servers, prune_versions)

        def _search_op_multi(self, api_obj, remote, tokens, test_value,
            case_sensitive=False, return_actions=True, num_to_return=None,
            start_point=None, servers=None, prune_versions=True):
                query = [api.Query(token, case_sensitive, return_actions,
                    num_to_return, start_point) for token in tokens]
                self._search_op_common(api_obj, remote, query, test_value,
                    return_actions, servers, prune_versions)

        def _search_op_common(self, api_obj, remote, query, test_value,
            return_actions, servers, prune_versions):
                self.debug("Search for: %s" % " ".join([str(q) for q in query]))
                search_func = api_obj.local_search
                if remote:
                        search_func = lambda x: api_obj.remote_search(x,
                            servers=servers, prune_versions=prune_versions)
                init_time = time.time()

                # servers may not be ready immediately - retry search
                # operation for 5 seconds

                while (time.time() - init_time) < 5:
                        try:
                                res = search_func(query)
                                if return_actions:
                                        res = self._extract_action_from_res(res)
                                else:
                                        res = self._extract_package_from_res(res)
                                res = set(res)
                                break
                        except api_errors.ProblematicSearchServers, e:
                                pass

                self._check(set(res), test_value)

        def _search_op_slow(self, api_obj, remote, token, test_value,
            case_sensitive=False, return_actions=True, num_to_return=None,
            start_point=None):
                query = [api.Query(token, case_sensitive, return_actions,
                    num_to_return, start_point)]
                self._search_op_slow_common(api_obj, query, test_value,
                    return_actions)

        def _search_op_slow_multi(self, api_obj, remote, tokens, test_value,
            case_sensitive=False, return_actions=True, num_to_return=None,
            start_point=None):
                query = [api.Query(token, case_sensitive, return_actions,
                    num_to_return, start_point) for token in tokens]
                self._search_op_slow_common(api_obj, query, test_value,
                    return_actions)

        def _search_op_slow_common(self, api_obj, query, test_value,
            return_actions):
                search_func = api_obj.local_search
                tmp = search_func(query)
                res = []
                ssu = False
                try:
                        for i in tmp:
                                res.append(i)
                except api_errors.SlowSearchUsed:
                        ssu = True
                self.assert_(ssu)
                if return_actions:
                        res = self._extract_action_from_res(res)
                else:
                        res = self._extract_package_from_res(res)
                res = set(res)
                self._check(set(res), test_value)

        def _run_full_remote_tests(self, api_obj):
                self._search_op(api_obj, True, "example_pkg",
                    self.res_remote_pkg)
                self._search_op(api_obj, True, "example_path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "(example_path)",
                    self.res_remote_path)
                self._search_op(api_obj, True, "<exam*:::>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "::com.sun.service.info_url:",
                    self.res_remote_url)
                self._search_op(api_obj, True, ":::e* AND *path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "e* AND *path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "<e*>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "<e*> AND <e*>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "<e*> OR <e*>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "<exam:::>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "exam:::e*path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "exam:::e*path AND e*:::",
                    self.res_remote_path)
                self._search_op(api_obj, True, "e*::: AND exam:::*path",
                    self.res_remote_path_extra)
                self._search_op(api_obj, True, "example*",
                    self.res_remote_wildcard)
                self._search_op(api_obj, True, "/bin", self.res_remote_bin)
                self._search_op(api_obj, True, "4851433",
                    self.res_remote_bug_id)
                self._search_op(api_obj, True, "<4851433> AND <4725245>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "4851433 AND 4725245",
                    self.res_remote_bug_id)
                self._search_op(api_obj, True,
                    "4851433 AND 4725245 OR example_path",
                    self.res_remote_bug_id)
                self._search_op(api_obj, True,
                    "4851433 AND (4725245 OR example_path)",
                    self.res_remote_bug_id)
                self._search_op(api_obj, True,
                    "(4851433 AND 4725245) OR example_path",
                    self.res_remote_bug_id | self.res_remote_path)
                self._search_op(api_obj, True, "4851433 OR 4725245",
                    self.res_remote_bug_id | self.res_remote_bug_id_4725245)
                self._search_op(api_obj, True, "6556919",
                    self.res_remote_inc_changes)
                self._search_op(api_obj, True, "6556?19",
                    self.res_remote_inc_changes)
                self._search_op(api_obj, True, "42",
                    self.res_remote_random_test)
                self._search_op(api_obj, True, "79",
                    self.res_remote_random_test_79)
                self._search_op(api_obj, True, "separator",
                    self.res_remote_keywords)
                self._search_op(api_obj, True, "\"sort 0x86\"",
                    self.res_remote_keywords)
                self._search_op(api_obj, True, "*example*",
                    self.res_remote_glob)
                self._search_op(api_obj, True, "fooo", self.res_remote_foo)
                self._search_op(api_obj, True, "fo*", self.res_remote_foo)
                self._search_op(api_obj, True, "bar", self.res_remote_foo)
                self._search_op(api_obj, True, "openssl",
                    self.res_remote_openssl)
                self._search_op(api_obj, True, "OPENSSL",
                    self.res_remote_openssl)
                self._search_op(api_obj, True, "OpEnSsL",
                    self.res_remote_openssl)
                # Test for bug 11235, case insensitive phrase search, and bug
                # 11354, mangled fields during phrase search.
                self._search_op(api_obj, True, "'OpEnSsL'",
                    self.res_remote_openssl)
                self._search_op(api_obj, True, "OpEnS*",
                    self.res_remote_openssl)

                # These tests are included because a specific bug
                # was found during development. This prevents regression back
                # to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self._search_op(api_obj, True, "a_non_existent_token", set())

                self._search_op(api_obj, True, "42 AND 4641790", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, True, "<e*> AND e*", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, True, "e* AND <e*>", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, True, "<e*> OR e*", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, True, "e* OR <e*>", set())
                # Test for bug 15284, \ not being treated as an escape character
                # for : as well as testing that \: when used with field queries
                # works as expected.
                svc_name = "svc\:/milestone/multi-user-server\:default"
                self._search_op(api_obj, True,
                    svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "example_pkg:set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "smf.fmri:%s" %svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    ":set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "%s *milestone*" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "example_pkg:set:smf.fmri:%s %s" % (svc_name, svc_name),
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "example_pkg:set:smf.fmri:%s example_pkg:set:smf.fmri:%s" %
                    (svc_name, svc_name),
                    self.res_smf_svc)
                self._search_op(api_obj, True,
                    "%s example_pkg:set:smf.fmri:%s" %
                    (svc_name, svc_name),
                    self.res_smf_svc)
                # Test that a single escaped colon doesn't cause a traceback.
                self._search_op(api_obj, True, "\:", set())
                
        def _run_remote_tests(self, api_obj):
                self._search_op(api_obj, True, "example_pkg",
                    self.res_remote_pkg)
                self._search_op(api_obj, True, "example_path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "::com.sun.service.info_url:",
                    self.res_remote_url)
                self._search_op(api_obj, True, "<e*>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "<exam:::>",
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, True, "exam:::e*path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "example*",
                    self.res_remote_wildcard)
                self._search_op(api_obj, True, "/bin", self.res_remote_bin)
                self._search_op(api_obj, True, "4851433",
                    self.res_remote_bug_id)
                self._search_op(api_obj, True, "4725245",
                    self.res_remote_bug_id_4725245)
                self._search_op(api_obj, True, "6556919",
                    self.res_remote_inc_changes)
                self._search_op(api_obj, True, "42",
                    self.res_remote_random_test)
                self._search_op(api_obj, True, "79",
                    self.res_remote_random_test_79)
                self._search_op(api_obj, True, "separator",
                    self.res_remote_keywords)
                self._search_op(api_obj, True, "\"sort 0x86\"",
                    self.res_remote_keywords)
                self._search_op(api_obj, True, "*example*",
                    self.res_remote_glob)
                self._search_op(api_obj, True, "fooo", self.res_remote_foo)
                self._search_op(api_obj, True, "bar", self.res_remote_foo)
                self._search_op(api_obj, True, "OpEnSsL",
                    self.res_remote_openssl)

                # These tests are included because a specific bug
                # was found during development. This prevents regression back
                # to that bug.
                self._search_op(api_obj, True, "a_non_existent_token", set())

        def _run_full_local_tests(self, api_obj):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(api_obj, False, "example_pkg",
                    self.res_local_pkg)
                self._search_op(api_obj, False, "example_path",
                    self.res_local_path)
                self._search_op(api_obj, False, "(example_path)",
                    self.res_local_path)
                self._search_op(api_obj, False, "<exam*:::>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "::com.sun.service.info_url:",
                    self.res_remote_url)
                self._search_op(api_obj, False, ":::e* AND *path",
                    self.res_local_path)
                self._search_op(api_obj, False, "e* AND *path",
                    self.res_local_path)
                self._search_op(api_obj, False, "<e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "<e*> AND <e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "<e*> OR <e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "<exam:::>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "exam:::e*path",
                    self.res_local_path)
                self._search_op(api_obj, False, "exam:::e*path AND e*:::",
                    self.res_local_path)
                self._search_op(api_obj, False, "e*::: AND exam:::*path",
                    self.res_remote_path_extra)
                self._search_op(api_obj, False, "example*",
                    self.res_local_wildcard)
                self._search_op(api_obj, False, "/bin", self.res_local_bin)
                self._search_op(api_obj, False, "4851433",
                    self.res_local_bug_id)
                self._search_op(api_obj, False, "<4851433> AND <4725245>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "4851433 AND 4725245",
                    self.res_local_bug_id)
                self._search_op(api_obj, False,
                    "4851433 AND 4725245 OR example_path",
                    self.res_local_bug_id)
                self._search_op(api_obj, False,
                    "4851433 AND (4725245 OR example_path)",
                    self.res_local_bug_id)
                self._search_op(api_obj, False,
                    "(4851433 AND 4725245) OR example_path",
                    self.res_local_bug_id | self.res_local_path)
                self._search_op(api_obj, False, "4851433 OR 4725245",
                    self.res_local_bug_id | self.res_remote_bug_id_4725245)
                self._search_op(api_obj, False, "6556919",
                    self.res_local_inc_changes)
                self._search_op(api_obj, False, "65569??",
                    self.res_local_inc_changes)
                self._search_op(api_obj, False, "42",
                    self.res_local_random_test)
                self._search_op(api_obj, False, "79",
                    self.res_remote_random_test_79)
                self._search_op(api_obj, False, "separator",
                    self.res_local_keywords)
                self._search_op(api_obj, False, "\"sort 0x86\"",
                    self.res_remote_keywords)
                self._search_op(api_obj, False, "*example*",
                    self.res_local_glob)
                self._search_op(api_obj, False, "fooo", self.res_local_foo)
                self._search_op(api_obj, False, "fo*", self.res_local_foo)
                self._search_op(api_obj, False, "bar", self.res_local_foo)
                self._search_op(api_obj, False, "openssl",
                    self.res_local_openssl)
                self._search_op(api_obj, False, "OPENSSL",
                    self.res_local_openssl)
                self._search_op(api_obj, False, "OpEnSsL",
                    self.res_local_openssl)
                # Test for bug 11235, case insensitive phrase search, and bug
                # 11354, mangled fields during phrase search.
                self._search_op(api_obj, False, "'OpEnSsL'",
                    self.res_remote_openssl)
                self._search_op(api_obj, False, "OpEnS*",
                    self.res_local_openssl)
                # These tests are included because a specific bug
                # was found during development. These tests prevent regression
                # back to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self._search_op(api_obj, False, "a_non_existent_token", set())
                self._search_op(api_obj, False, "42 AND 4641790", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, False, "<e*> AND e*", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, False, "e* AND <e*>", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, False, "<e*> OR e*", set())
                self.assertRaises(api_errors.BooleanQueryException,
                    self._search_op, api_obj, False, "e* OR <e*>", set())
                # Test for bug 15284, \ not being treated as an escape character
                # for : as well as testing that \: when used with field queries
                # works as expected.
                svc_name = "svc\:/milestone/multi-user-server\:default"
                self._search_op(api_obj, False,
                    svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "example_pkg:set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "smf.fmri:%s" %svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    ":set:smf.fmri:%s" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "%s *milestone*" % svc_name,
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "example_pkg:set:smf.fmri:%s %s" % (svc_name, svc_name),
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "example_pkg:set:smf.fmri:%s example_pkg:set:smf.fmri:%s" %
                    (svc_name, svc_name),
                    self.res_smf_svc)
                self._search_op(api_obj, False,
                    "%s example_pkg:set:smf.fmri:%s" %
                    (svc_name, svc_name),
                    self.res_smf_svc)
                # Test that a single escaped colon doesn't cause a traceback.
                self._search_op(api_obj, True, "\:", set())

        def _run_local_tests(self, api_obj):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(api_obj, False, "example_pkg",
                    self.res_local_pkg)
                self._search_op(api_obj, False, "example_path",
                    self.res_local_path)
                self._search_op(api_obj, False, "::com.sun.service.info_url:",
                    self.res_remote_url)
                self._search_op(api_obj, False, "<e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "<exam:::>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op(api_obj, False, "exam:::e*path",
                    self.res_local_path)
                self._search_op(api_obj, False, "example*",
                    self.res_local_wildcard)
                self._search_op(api_obj, False, "/bin", self.res_local_bin)
                self._search_op(api_obj, False, "4851433",
                    self.res_local_bug_id)
                self._search_op(api_obj, False, "4725245",
                    self.res_remote_bug_id_4725245)
                self._search_op(api_obj, False, "6556919",
                    self.res_local_inc_changes)
                self._search_op(api_obj, False, "42",
                    self.res_local_random_test)
                self._search_op(api_obj, False, "79",
                    self.res_remote_random_test_79)
                self._search_op(api_obj, False, "separator",
                    self.res_local_keywords)
                self._search_op(api_obj, False, "\"sort 0x86\"",
                    self.res_remote_keywords)
                self._search_op(api_obj, False, "*example*",
                    self.res_local_glob)
                self._search_op(api_obj, False, "fooo", self.res_local_foo)
                self._search_op(api_obj, False, "bar", self.res_local_foo)
                self._search_op(api_obj, False, "OpEnSsL",
                    self.res_local_openssl)
                # These tests are included because a specific bug
                # was found during development. These tests prevent regression
                # back to that bug.
                self._search_op(api_obj, False, "a_non_existent_token", set())

        def _run_degraded_local_tests(self, api_obj):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op_slow(api_obj, False, "example_pkg",
                    self.res_local_pkg)
                self._search_op_slow(api_obj, False, "example_path",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "(example_path)",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "<exam*:::>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False,
                    "::com.sun.service.info_url:",
                    self.res_remote_url)
                self._search_op_slow(api_obj, False, ":::e* AND *path",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "e* AND *path",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "<e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False, "<e*> AND <e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False, "<e*> OR <e*>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False, "<exam:::>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False, "exam:::e*path",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "exam:::e*path AND e*:::",
                    self.res_local_path)
                self._search_op_slow(api_obj, False, "e*::: AND exam:::*path",
                    self.res_remote_path_extra)
                self._search_op_slow(api_obj, False, "example*",
                    self.res_local_wildcard)
                self._search_op_slow(api_obj, False, "/bin", self.res_local_bin)
                self._search_op_slow(api_obj, False, "4851433",
                    self.res_local_bug_id)
                self._search_op_slow(api_obj, False, "<4851433> AND <4725245>",
                    self.res_local_pkg_ret_pkg, return_actions=False)
                self._search_op_slow(api_obj, False, "4851433 AND 4725245",
                    self.res_local_bug_id)
                self._search_op_slow(api_obj, False,
                    "4851433 AND 4725245 OR example_path",
                    self.res_local_bug_id)
                self._search_op_slow(api_obj, False,
                    "4851433 AND (4725245 OR example_path)",
                    self.res_local_bug_id)
                self._search_op_slow(api_obj, False,
                    "(4851433 AND 4725245) OR example_path",
                    self.res_local_bug_id | self.res_local_path)
                self._search_op_slow(api_obj, False, "4851433 OR 4725245",
                    self.res_local_bug_id | self.res_remote_bug_id_4725245)
                self._search_op_slow(api_obj, False, "6556919",
                    self.res_local_inc_changes)
                self._search_op_slow(api_obj, False, "65569??",
                    self.res_local_inc_changes)
                self._search_op_slow(api_obj, False, "42",
                    self.res_local_random_test)
                self._search_op_slow(api_obj, False, "79",
                    self.res_remote_random_test_79)
                self._search_op_slow(api_obj, False, "separator",
                    self.res_local_keywords)
                self._search_op_slow(api_obj, False, "\"sort 0x86\"",
                    self.res_remote_keywords)
                self._search_op_slow(api_obj, False, "*example*",
                    self.res_local_glob)
                self._search_op_slow(api_obj, False, "fooo", self.res_local_foo)
                self._search_op_slow(api_obj, False, "fo*", self.res_local_foo)
                self._search_op_slow(api_obj, False, "bar", self.res_local_foo)
                self._search_op_slow(api_obj, False, "openssl",
                    self.res_local_openssl)
                self._search_op_slow(api_obj, False, "OPENSSL",
                    self.res_local_openssl)
                self._search_op_slow(api_obj, False, "OpEnSsL",
                    self.res_local_openssl)
                self._search_op_slow(api_obj, False, "OpEnS*",
                    self.res_local_openssl)
                # These tests are included because a specific bug
                # was found during development. These tests prevent regression
                # back to that bug. Exit status of 1 is expected because the
                # token isn't in the packages.
                self._search_op_slow(api_obj, False, "a_non_existent_token",
                    set())

        def _run_remove_root_search(self, search_func, remote, api_obj, ip):
                search_func(api_obj, remote, [ip + "example_pkg"], set())
                search_func(api_obj, remote, [ip + "bin/example_path"],
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote, ["(%sbin/example_path)" % ip],
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote, ["<%sexam*:::>" % ip],
                    set(), return_actions=False)
                search_func(api_obj, remote,
                    ["::%scom.sun.service.info_url:" % ip], set())
                search_func(api_obj, remote,
                    ["%sbin/e* AND %s*path" % (ip, ip)],
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote,
                    ["(4851433 AND 4725245) OR :file::%sbin/example_path" % ip],
                    self.res_remote_bug_id |
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote,
                    [":::%sbin/example_path OR (4851433 AND 4725245)" % ip],
                    self.res_remote_bug_id |
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote,
                    ["%sbin/example_path OR %sbin/example_path" % (ip, ip)],
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote,
                    ["<::path:%sbin/example_path> OR <(a AND b)>" % ip],
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                search_func(api_obj, remote,
                    ["<(a AND b)> OR <%sbin/example_path>" % ip],
                    self.res_remote_pkg_ret_pkg, return_actions=False)
                # The tests below here are for testing that multiple queries
                # to search return the results from both queries (bug 10365)
                search_func(api_obj, remote,
                    ["<(a AND b)>",  "example_path"],
                    self.res_remote_path)
                search_func(api_obj, remote,
                    ["example_path", "<(a AND b)>"],
                    self.res_remote_path)
                search_func(api_obj, remote,
                    [":::%sbin/example_path" % ip, "(4851433 AND 4725245)"],
                    self.res_remote_bug_id |
                    self.res_remote_path_of_example_path)
                search_func(api_obj, remote,
                    ["(4851433 AND 4725245)", ":::%sbin/example_path" % ip],
                    self.res_remote_bug_id |
                    self.res_remote_path_of_example_path)

        def _run_local_tests_example11_installed(self, api_obj):
                outfile = os.path.join(self.testdata_dir, "res")

                # This finds something because the client side
                # manifest has had the name of the package inserted
                # into it.

                self._search_op(api_obj, False, "example_pkg",
                    self.res_local_pkg_example11)
                self._search_op(api_obj, False, "example_path", set())
                self._search_op(api_obj, False, "example_path11",
                    self.res_local_path_example11)
                self._search_op(api_obj, False, "example*",
                    self.res_local_wildcard_example11)
                self._search_op(api_obj, False, "/bin",
                    self.res_local_bin_example11)

        def _run_local_empty_tests(self, api_obj):
                self._search_op(api_obj, False, "example_pkg", set())
                self._search_op(api_obj, False, "example_path", set())
                self._search_op(api_obj, False, "example*", set())
                self._search_op(api_obj, False, "/bin", set())

        def _run_remote_empty_tests(self, api_obj):
                self._search_op(api_obj, True, "example_pkg", set())
                self._search_op(api_obj, True, "example_path", set())
                self._search_op(api_obj, True, "example*", set())
                self._search_op(api_obj, True, "/bin", set())
                self._search_op(api_obj, True, "*unique*", set())

        @staticmethod
        def _restore_dir(index_dir, index_dir_tmp):
                shutil.rmtree(index_dir)
                shutil.move(index_dir_tmp, index_dir)

        @staticmethod
        def _restore_dir_preserve_hash(index_dir, index_dir_tmp):
                tmp_file = "full_fmri_list.hash"
                portable.remove(os.path.join(index_dir_tmp, tmp_file))
                shutil.move(os.path.join(index_dir, tmp_file),
                            index_dir_tmp)
                fh = open(os.path.join(index_dir_tmp, ss.MAIN_FILE), "r")
                fh.seek(0)
                fh.seek(9)
                ver = fh.read(1)
                fh.close()
                fh = open(os.path.join(index_dir_tmp, tmp_file), "r+")
                fh.seek(0)
                fh.seek(9)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("%s" % ver)
                shutil.rmtree(index_dir)
                shutil.move(index_dir_tmp, index_dir)

        def _get_index_dirs(self):
                index_dir = os.path.join(self.img_path, "var","pkg","index")
                index_dir_tmp = index_dir + "TMP"
                return index_dir, index_dir_tmp

        @staticmethod
        def _overwrite_version_number(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(9)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("0")
                fh.close()

        @staticmethod
        def _overwrite_on_disk_format_version_number(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(16)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("9")
                fh.close()

        @staticmethod
        def _overwrite_on_disk_format_version_number_with_letter(file_path):
                fh = open(file_path, "r+")
                fh.seek(0)
                fh.seek(16)
                # Overwrite the existing version number.
                # By definition, the version 0 is never used.
                fh.write("a")
                fh.close()

        @staticmethod
        def _replace_on_disk_format_version(dir):
                file_path = os.path.join(dir, ss.BYTE_OFFSET_FILE)
                fh = open(file_path, "r")
                lst = fh.readlines()
                fh.close()
                fh = open(file_path, "w")
                fh.write(lst[0])
                for l in lst[2:]:
                        fh.write(l)
                fh.close()

        @staticmethod
        def _overwrite_hash(ffh_path):
                fd, tmp = tempfile.mkstemp()
                portable.copyfile(ffh_path, tmp)
                fh = open(tmp, "r+")
                fh.seek(0)
                fh.seek(20)
                fh.write("*")
                fh.close()
                portable.rename(tmp, ffh_path)

        def _check_no_index(self):
                ind_dir, ind_dir_tmp = self._get_index_dirs()
                if os.listdir(ind_dir):
                        self.assert_(0)
                if os.path.exists(ind_dir_tmp):
                        self.assert_(0)

        def _do_install(self, api_obj, pkg_list, **kwargs):
                self.debug("install %s" % " ".join(pkg_list))
                api_obj.plan_install(pkg_list, **kwargs)
                self._do_finish(api_obj)

        def _do_uninstall(self, api_obj, pkg_list, **kwargs):
                self.debug("uninstall %s" % " ".join(pkg_list))
                api_obj.plan_uninstall(pkg_list, False, **kwargs)
                self._do_finish(api_obj)

        def _do_image_update(self, api_obj, **kwargs):
                self.debug("planning image-update")
                api_obj.plan_update_all(sys.argv[0], verbose=False, **kwargs)
                self._do_finish(api_obj)

        def _do_finish(self, api_obj):
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

        @staticmethod
        def validateAssertRaises(ex_type, validate_func, func, *args, **kwargs):
                try:
                        func(*args, **kwargs)
                except ex_type, e:
                        validate_func(e)
                else:
                        raise RuntimeError("Didn't raise expected exception.")

        @staticmethod
        def _check_err(e, expected_str, expected_code):
                err = e.read()
                if expected_code != e.code:
                        raise RuntimeError("Got wrong code, expected %s got "
                            "%s" % (expected_code, e.code))
                if expected_str not in err:
                        raise RuntimeError("Got unexpected error message of:\n"
                            "%s" % err)


class TestApiSearchBasicsP(TestApiSearchBasics):
        # Only start/stop the depot once (instead of for every test)
        persistent_setup = True

        def __init__(self, *args, **kwargs):
                TestApiSearchBasics.__init__(self, *args, **kwargs)
                self.sent_pkgs = set()

        def pkgsend_bulk(self, durl, pkg, optional=True):
                if pkg not in self.sent_pkgs or optional == False:
                        self.sent_pkgs.add(pkg)
                        TestApiSearchBasics.pkgsend_bulk(self, durl, pkg)

        def setUp(self):
                TestApiSearchBasics.setUp(self)
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.fat_pkg10)
                self.pkgsend_bulk(durl, self.another_pkg10)

        def test_010_remote(self):
                """Test remote search."""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                time.sleep(1)
                # This should be a full test to test all functionality.
                self._run_full_remote_tests(api_obj)
                self._search_op(api_obj, True, ":file::", self.res_remote_file)

        def test_020_local_0(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["example_pkg"])

                self._run_full_local_tests(api_obj)

        def test_030_degraded_local(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["example_pkg@1.0"])

                index_dir = os.path.join(self.img_path, "var","pkg","index")
                shutil.rmtree(index_dir)

                self._run_degraded_local_tests(api_obj)

        def test_040_repeated_install_uninstall(self):
                """Install and uninstall a package. Checking search both
                after each change to the image."""
                # During development, the index could become corrupted by
                # repeated installing and uninstalling a package. This
                # tests if that has been fixed.
                repeat = 3

                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["example_pkg@1.0"])
                self._do_uninstall(api_obj, ["example_pkg"])

                for i in range(1, repeat):
                        self._do_install(api_obj, ["example_pkg"])
                        self._run_local_tests(api_obj)
                        self._do_uninstall(api_obj, ["example_pkg"])
                        api_obj.reset()
                        self._run_local_empty_tests(api_obj)

        def test_050_local_case_sensitive(self):
                """Test local case sensitive search"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["example_pkg@1.0"])
                self._search_op(api_obj, False, "fooo", set(), True)
                self._search_op(api_obj, False, "fo*", set(), True)
                self._search_op(api_obj, False, "bar", set(), True)
                self._search_op(api_obj, False, "FOOO", self.res_local_foo,
                    True)
                self._search_op(api_obj, False, "bAr", self.res_local_foo, True)

        def test_060_missing_files(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()

                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self._do_install(api_obj, ["example_pkg@1.0"])

                index_dir = os.path.join(self.img_path, "var","pkg","index")

                first = True

                for d in query_parser.TermQuery._global_data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        portable.rename(orig_path, dest_path)
                        self.assertRaises(api_errors.InconsistentIndexException,
                            self._search_op, api_obj, False,
                            "exam:::example_pkg", [])
                        if first:
                                # Run the shell version once to check that no
                                # stack trace happens.
                                self.pkg("search -l 'exam:::example_pkg'",
                                    exit=1)
                                first = False
                        portable.rename(dest_path, orig_path)
                        self._search_op(api_obj, False, "exam:::example_pkg",
                            self.res_local_pkg)

        def test_070_mismatched_versions(self):
                """Test to check for stack trace when files missing.
                Bug 2753"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self._do_install(api_obj, ["example_pkg@1.0"])

                index_dir = os.path.join(self.img_path, "var","pkg","index")

                first = True

                for d in query_parser.TermQuery._global_data_dict.values():
                        orig_fn = d.get_file_name()
                        orig_path = os.path.join(index_dir, orig_fn)
                        dest_fn = orig_fn + "TMP"
                        dest_path = os.path.join(index_dir, dest_fn)
                        shutil.copy(orig_path, dest_path)
                        self._overwrite_version_number(orig_path)
                        api_obj.reset()
                        self.assertRaises(api_errors.InconsistentIndexException,
                            self._search_op, api_obj, False,
                            "exam:::example_pkg", [])
                        if first:
                                # Run the shell version once to check that no
                                # stack trace happens.
                                self.pkg("search -l 'exam:::example_pkg'",
                                    exit=1)
                                first = False
                        portable.rename(dest_path, orig_path)
                        self._search_op(api_obj, False, "example_pkg",
                            self.res_local_pkg)
                        self._overwrite_version_number(orig_path)
                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_uninstall, api_obj, ["example_pkg"])
                        api_obj.reset()
                        self._search_op(api_obj, False, "example_pkg", set())
                        self._overwrite_version_number(orig_path)
                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_install, api_obj, ["example_pkg"])
                        api_obj.reset()
                        self._search_op(api_obj, False, "example_pkg",
                            self.res_local_pkg)

                ffh = ss.IndexStoreSetHash(ss.FULL_FMRI_HASH_FILE)
                ffh_path = os.path.join(index_dir, ffh.get_file_name())
                dest_fh, dest_path = tempfile.mkstemp()
                shutil.copy(ffh_path, dest_path)
                self._overwrite_hash(ffh_path)
                self.assertRaises(api_errors.IncorrectIndexFileHash,
                    self._search_op, api_obj, False, "example_pkg", set())
                # Run the shell version of the test to check for a stack trace.
                self.pkg("search -l 'exam:::example_pkg'", exit=1)
                portable.rename(dest_path, ffh_path)
                self._search_op(api_obj, False, "example_pkg",
                    self.res_local_pkg)
                self._overwrite_hash(ffh_path)
                self.assertRaises(api_errors.WrapSuccessfulIndexingException,
                    self._do_uninstall, api_obj, ["example_pkg"])
                self._search_op(api_obj, False, "example_pkg", set())

        def test_080_weird_patterns(self):
                """Test strange patterns to ensure they're handled correctly"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._search_op(api_obj, True, "[*]", self.res_remote_weird)
                self._search_op(api_obj, True, "[?]", self.res_remote_weird)
                self._search_op(api_obj, True, "[[]", self.res_remote_weird)
                self._search_op(api_obj, True, "[]]", self.res_remote_weird)
                self._search_op(api_obj, True, "FO[O]O", self.res_remote_foo)
                self._search_op(api_obj, True, "FO[?O]O", self.res_remote_foo)
                self._search_op(api_obj, True, "FO[*O]O", self.res_remote_foo)
                self._search_op(api_obj, True, "FO[]O]O", self.res_remote_foo)

        def test_090_bug_7660(self):
                """Test that installing a package doesn't prevent searching on
                package names from working on previously installed packages."""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                tmp_dir = os.path.join(self.img_path, "var", "pkg", "index",
                    "TMP")
                self._do_install(api_obj, ["example_pkg"])
                api_obj.rebuild_search_index()
                self._do_install(api_obj, ["fat"])
                self.assert_(not os.path.exists(tmp_dir))
                self._run_local_tests(api_obj)

        def test_100_bug_6712_i386(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()

                self.image_create(durl,
                    additional_args="--variant variant.arch=i386")

                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                remote = True

                self._search_op(api_obj, remote, "fat:::*",
                    self.res_remote_fat10_star)
                self._do_install(api_obj, ["fat"])
                remote = False
                self._search_op(api_obj, remote, "fat:::*",
                    self.res_local_fat10_i386_star)

        def test_110_bug_6712_sparc(self):
                """Install one package, and run the search suite."""
                durl = self.dc.get_depot_url()

                self.image_create(durl,
                    additional_args="--variant variant.arch=sparc")
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                remote = True

                self._search_op(api_obj, remote, "fat:::*",
                    self.res_remote_fat10_star)
                self._do_install(api_obj, ["fat"])
                remote = False
                self._search_op(api_obj, remote, "fat:::*",
                    self.res_local_fat10_sparc_star)

        def test_120_bug_3046(self):
                """Checks if directories ending in / break the indexer."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bad_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self._search_op(api_obj, True, "foo", set())
                self._search_op(api_obj, True, "/", set())

        def test_130_bug_1059(self):
                """Checks whether the fallback of removing the image root works.
                Also tests whether multiple queries submitted via the api work.
                """
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                ip = self.get_img_path()
                if not ip.endswith("/"):
                        ip += "/"

                # Do remote searches
                self._run_remove_root_search(self._search_op_multi, True,
                    api_obj, ip)

                self._do_install(api_obj, ["example_pkg"])
                # Do local searches
                self._run_remove_root_search(self._search_op_multi, False,
                    api_obj, ip)

                index_dir = os.path.join(self.img_path, "var","pkg","index")
                shutil.rmtree(index_dir)
                # Do slow local searches
                self._run_remove_root_search(self._search_op_slow_multi, False,
                    api_obj, ip)

        def test_bug_2849(self):
                """Checks if things with spaces break the indexer."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.space_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["space_pkg"])
                time.sleep(1)

                self.pkgsend_bulk(durl, self.space_pkg10, optional=False)
                api_obj.refresh(immediate=True)

                self._do_install(api_obj, ["space_pkg"])

                remote = False
                self._search_op(api_obj, remote, 'with', set())
                self._search_op(api_obj, remote, 'with*',
                    self.res_space_with_star)
                self._search_op(api_obj, remote, '*space',
                    self.res_space_space_star)
                self._search_op(api_obj, remote, 'space', set())
                self._search_op(api_obj, remote, 'unique_dir',
                    self.res_space_unique)
                remote = True
                self._search_op(api_obj, remote, 'with', set())
                self._search_op(api_obj, remote, 'with*',
                    self.res_space_with_star)
                self._search_op(api_obj, remote, '*space',
                    self.res_space_space_star)
                self._search_op(api_obj, remote, 'space', set())
                time.sleep(1)
                self.pkgsend_bulk(durl, self.space_pkg10, optional=False)
                # Need to add install of subsequent package and
                # local side search as well as remote
                self._search_op(api_obj, remote, 'with', set())
                self._search_op(api_obj, remote, 'with*',
                    self.res_space_with_star)
                self._search_op(api_obj, remote, '*space',
                    self.res_space_space_star)
                self._search_op(api_obj, remote, 'space', set())
                self._search_op(api_obj, remote, 'unique_dir',
                    self.res_space_unique)

        def test_bug_2863(self):
                """Check that disabling indexing works as expected"""
                durl = self.dc.get_depot_url()
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._check_no_index()
                self._do_install(api_obj, ["example_pkg"], update_index=False)
                self._check_no_index()
                api_obj.rebuild_search_index()
                self._run_local_tests(api_obj)
                self._do_uninstall(api_obj, ["example_pkg"], update_index=False)
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self.assertRaises(api_errors.IncorrectIndexFileHash,
                    self._search_op, api_obj, False, "example_pkg", set())
                api_obj.rebuild_search_index()
                self._run_local_empty_tests(api_obj)
                self._do_install(api_obj, ["example_pkg"])
                self._run_local_tests(api_obj)
                self.pkgsend_bulk(durl, self.example_pkg11)
                api_obj.refresh(immediate=True)
                self._do_image_update(api_obj, update_index=False)
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self.assertRaises(api_errors.IncorrectIndexFileHash,
                    self._search_op, api_obj, False, "example_pkg", set())
                api_obj.rebuild_search_index()
                self._run_local_tests_example11_installed(api_obj)
                self._do_uninstall(api_obj, ["example_pkg"], update_index=False)
                # Running empty test because search will notice the index
                # does not match the installed packages and complain.
                self.assertRaises(api_errors.IncorrectIndexFileHash,
                    self._search_op, api_obj, False, "example_pkg", set())
                api_obj.rebuild_search_index()
                self._run_local_empty_tests(api_obj)

        def test_bug_2989_1(self):
                durl = self.dc.get_depot_url()

                for f in self._dir_restore_functions:
                        self.image_create(durl)
                        progresstracker = progress.NullProgressTracker()
                        api_obj = api.ImageInterface(self.get_img_path(),
                            API_VERSION, progresstracker, lambda x: False,
                            PKG_CLIENT_NAME)
                        api_obj.rebuild_search_index()

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)

                        self._do_install(api_obj, ["example_pkg"])

                        f(index_dir, index_dir_tmp)

                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_uninstall, api_obj, ["example_pkg"])

                        self.image_destroy()

        def test_bug_2989_2(self):
                durl = self.dc.get_depot_url()

                for f in self._dir_restore_functions:

                        self.image_create(durl)
                        progresstracker = progress.NullProgressTracker()
                        api_obj = api.ImageInterface(self.get_img_path(),
                            API_VERSION, progresstracker, lambda x: False,
                            PKG_CLIENT_NAME)
                        self._do_install(api_obj, ["example_pkg"])

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)

                        self._do_install(api_obj, ["another_pkg"])

                        f(index_dir, index_dir_tmp)

                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_uninstall, api_obj, ["another_pkg"])

                        self.image_destroy()

        def test_bug_2989_3(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg11)

                for f in self._dir_restore_functions:

                        self.image_create(durl)
                        progresstracker = progress.NullProgressTracker()
                        api_obj = api.ImageInterface(self.get_img_path(),
                            API_VERSION, progresstracker, lambda x: False,
                            PKG_CLIENT_NAME)
                        self._do_install(api_obj, ["example_pkg@1.0,5.11-0"])

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)

                        self._do_install(api_obj, ["example_pkg"])

                        f(index_dir, index_dir_tmp)

                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_uninstall, api_obj, ["example_pkg"])

                        self.image_destroy()

        def test_bug_2989_4(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg11)

                for f in self._dir_restore_functions:

                        self.image_create(durl)
                        progresstracker = progress.NullProgressTracker()
                        api_obj = api.ImageInterface(self.get_img_path(),
                            API_VERSION, progresstracker, lambda x: False,
                            PKG_CLIENT_NAME)
                        self._do_install(api_obj, ["another_pkg"])

                        index_dir, index_dir_tmp = self._get_index_dirs()

                        shutil.copytree(index_dir, index_dir_tmp)

                        self._do_install(api_obj, ["example_pkg@1.0,5.11-0"])

                        f(index_dir, index_dir_tmp)

                        self.assertRaises(
                            api_errors.WrapSuccessfulIndexingException,
                            self._do_image_update, api_obj)

                        self.image_destroy()

        def test_bug_4239(self):
                """Tests whether categories are indexed and searched for
                correctly."""

                def _run_cat_tests(self, remote):
                        self._search_op(api_obj, remote, "System",
                            self.res_cat_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "Security",
                            self.res_cat_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "System/Security",
                            self.res_cat_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "Other/Category",
                            self.res_cat_pkg10_2, case_sensitive=False)
                        self._search_op(api_obj, remote, "Other",
                            self.res_cat_pkg10_2, case_sensitive=False)
                        self._search_op(api_obj, remote, "Category",
                            self.res_cat_pkg10_2, case_sensitive=False)

                def _run_cat2_tests(self, remote):
                        self._search_op(api_obj, remote, "Applications",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(api_obj, True, "Sound",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "Sound and Video",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "Sound*",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "*Video",
                            self.res_cat2_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote,
                            "'Applications/Sound and Video'",
                            self.res_cat2_pkg10, case_sensitive=False)
                        # This is a test for bug 11002 which ensures that the
                        # unquoting is being performed correctly.
                        self._search_op(api_obj, remote,
                            "'Applications/Sound%20and%20Video'",
                            set(), case_sensitive=False)
                        self._search_op(api_obj, remote, "Developer/C",
                            self.res_cat2_pkg10_2, case_sensitive=False)
                        self._search_op(api_obj, remote, "Developer",
                            self.res_cat2_pkg10_2, case_sensitive=False)
                        self._search_op(api_obj, remote, "C",
                            self.res_cat2_pkg10_2, case_sensitive=False)

                def _run_cat3_tests(self, remote):
                        self._search_op(api_obj, remote, "foo",
                            self.res_cat3_pkg10,case_sensitive=False)
                        self._search_op(api_obj, remote, "baz",
                            self.res_cat3_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote, "asda",
                            self.res_cat3_pkg10, case_sensitive=False)
                        self._search_op(api_obj, remote,
                            "foo/bar/baz/bill/beam/asda", self.res_cat3_pkg10,
                            case_sensitive=False)

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.cat_pkg10)
                self.pkgsend_bulk(durl, self.cat2_pkg10)
                self.pkgsend_bulk(durl, self.cat3_pkg10)
                self.pkgsend_bulk(durl, self.bad_cat_pkg10)
                self.pkgsend_bulk(durl, self.bad_cat2_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                remote = True
                _run_cat_tests(self, remote)
                _run_cat2_tests(self, remote)
                _run_cat3_tests(self, remote)

                remote = False
                self._do_install(api_obj, ["cat"])
                _run_cat_tests(self, remote)

                self._do_install(api_obj, ["cat2"])
                _run_cat2_tests(self, remote)

                self._do_install(api_obj, ["cat3"])
                _run_cat3_tests(self, remote)

                self._do_install(api_obj, ["badcat"])
                self._do_install(api_obj, ["badcat2"])
                _run_cat_tests(self, remote)
                _run_cat2_tests(self, remote)
                _run_cat3_tests(self, remote)

        def test_bug_7628(self):
                """Checks whether incremental update generates wrong
                additional lines."""
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                ind_dir = os.path.join(depotpath, "index")
                tok_file = os.path.join(ind_dir, ss.BYTE_OFFSET_FILE)
                main_file = os.path.join(ind_dir, ss.MAIN_FILE)
                self.pkgsend_bulk(durl, self.example_pkg10)
                time.sleep(1)
                fh = open(tok_file)
                tok_1 = fh.readlines()
                tok_len = len(tok_1)
                fh.close()
                fh = open(main_file)
                main_1 = fh.readlines()
                main_len = len(main_1)
                self.pkgsend_bulk(durl, self.example_pkg10, optional=False)
                time.sleep(1)
                fh = open(tok_file)
                tok_2 = fh.readlines()
                new_tok_len = len(tok_2)
                fh.close()
                fh = open(main_file)
                main_2 = fh.readlines()
                new_main_len = len(main_2)
                fh.close()
                # Since the server now adds a set action for the FMRI to
                # manifests during publication, there should be one
                # additional line for the token file.
                self.assertEqual(new_tok_len, tok_len + 1)
                self.assertEqual(new_main_len, main_len + 1)

        def test_bug_983(self):
                """Test for known bug 983."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bug_983_manifest)
                time.sleep(2)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._search_op(api_obj, True, "gmake", self.res_bug_983)
                self._search_op(api_obj, True, "SUNWcsl@0.5.11-0.89",
                    self.res_983_csl_dependency)
                self._search_op(api_obj, True, "SUNWcsl",
                    self.res_983_csl_dependency)
                self._search_op(api_obj, True, "SUNWtestbar@0.5.11-0.111",
                    self.res_983_bar_dependency)
                self._search_op(api_obj, True, "SUNWtestbar",
                    self.res_983_bar_dependency)
                self._search_op(api_obj, True, "SUNWtestfoo@0.5.11-0.111",
                    self.res_983_foo_dependency)
                self._search_op(api_obj, True, "SUNWtestfoo",
                    self.res_983_foo_dependency)
                self._search_op(api_obj, True, "depend:require:",
                    self.res_983_csl_dependency | self.res_983_bar_dependency)
                self._search_op(api_obj, True, "depend:incorporate:",
                    self.res_983_foo_dependency)
                self._search_op(api_obj, True, "depend::",
                    self.res_983_csl_dependency | self.res_983_bar_dependency |
                    self.res_983_foo_dependency)

        def test_bug_7534(self):
                """Tests that an automatic reindexing is detected by the test
                suite."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                index_dir = os.path.join(self.img_path, "var","pkg","index")

                orig_fn = os.path.join(index_dir,
                    query_parser.TermQuery._global_data_dict.values()[0].\
                    get_file_name())
                dest_fn = orig_fn + "TMP"

                self._do_install(api_obj, ["example_pkg"])
                api_obj.rebuild_search_index()

                portable.rename(orig_fn, dest_fn)
                self.assertRaises(api_errors.WrapSuccessfulIndexingException,
                    self._do_uninstall, api_obj, ["example_pkg"])

        def test_bug_8492(self):
                """Tests that field queries and phrase queries work together.
                """
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.bug_8492_manf_1)
                self.pkgsend_bulk(durl, self.bug_8492_manf_2)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self._search_op(api_obj, True, "set::'image packaging'",
                    self.res_8492_1 | self.res_8492_2)
                self._search_op(api_obj, True, "b1:set::'image packaging'",
                    self.res_8492_1)

                self._do_install(api_obj, ["b1", "b2"])

                self._search_op(api_obj, False, "set::'image packaging'",
                    self.res_8492_1 | self.res_8492_2)
                self._search_op(api_obj, False, "b2:set::'image packaging'",
                    self.res_8492_2)

                api_obj.rebuild_search_index()

                self._search_op(api_obj, True, "set::'image packaging'",
                    self.res_8492_1 | self.res_8492_2)
                self._search_op(api_obj, True, "b1:set::'image packaging'",
                    self.res_8492_1)

        def test_bug_9845_01(self):
                """Test that a corrupt query doesn't break the server."""
                durl = self.dc.get_depot_url()
                expected_string = _("A query is expected to have five fields: "
                    "case sensitivity, return type, number of results to "
                    "return, the number at which to start returning results, "
                    "and the text of the query.  The query provided lacked at "
                    "least one of those fields:")
                expected_code = 404
                q_str = "foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_02(self):
                """Test that a corrupt case_sensitive value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "case_sensitive",
                    "bv": "FAlse"
                }
                expected_code = 404
                q_str = "FAlse_2_None_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_03(self):
                """Test that a corrupt return_type value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "return_type",
                    "bv": "3"
                }
                expected_code = 404
                q_str = "False_3_None_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_04(self):
                """Test that a corrupt return_type value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "return_type",
                    "bv": "A"
                }
                expected_code = 404
                q_str = "False_A_None_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_05(self):
                """Test that a corrupt num_to_return value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "num_to_return",
                    "bv": "NOne"
                }
                expected_code = 404
                q_str = "False_2_NOne_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_06(self):
                """Test that a corrupt start_point value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "start_point",
                    "bv": "NOne"
                }
                expected_code = 404
                q_str = "False_2_None_NOne_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_07(self):
                """Test that a corrupt case_sensitive value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "case_sensitive",
                    "bv": ""
                }
                expected_code = 404
                q_str = "_2_None_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_08(self):
                """Test that a missing return_type value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "return_type",
                    "bv": ""
                }
                expected_code = 404
                q_str = "False__None_None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_09(self):
                """Test that a missing num_to_return value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "num_to_return",
                    "bv": ""
                }
                expected_code = 404
                q_str = "False_2__None_foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_10(self):
                """Test that a missing start_point value doesn't break the "
                server."""
                durl = self.dc.get_depot_url()
                expected_string = _("%(name)s had a bad value of '%(bv)s'") % {
                    "name": "start_point",
                    "bv": ""
                }
                expected_code = 404
                q_str = "False_2_None__foo"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_9845_11(self):
                """Test that missing query text doesn't break the server."""
                durl = self.dc.get_depot_url()
                expected_string = _("Could not parse query.")
                expected_code = 400
                q_str = "False_2_None_None_"
                self.validateAssertRaises(urllib2.HTTPError,
                    lambda x: self._check_err(x, expected_string,
                        expected_code),
                    urllib2.urlopen, durl + "/search/1/" + q_str)

        def test_bug_14177(self):
                def run_tests(api_obj, remote):
                        self._search_op(api_obj, remote, "pfoo",
                            self.hierarchical_named_pkg_res,
                            case_sensitive=False)
                        self._search_op(api_obj, remote, "pc/pfoo",
                            self.hierarchical_named_pkg_res,
                            case_sensitive=False)
                        self._search_op(api_obj, remote, "pb/pc/pfoo",
                            self.hierarchical_named_pkg_res,
                            case_sensitive=False)
                        self._search_op(api_obj, remote, "pa/pb/pc/pfoo",
                            self.hierarchical_named_pkg_res,
                            case_sensitive=False)
                        self._search_op(api_obj, remote, "test/pa/pb/pc/pfoo",
                            self.hierarchical_named_pkg_res,
                            case_sensitive=False)

                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.hierarchical_named_pkg)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                remote = True
                run_tests(api_obj, remote)
                self._do_install(api_obj, ["pfoo"])
                remote = False
                run_tests(api_obj, remote)
                api_obj.rebuild_search_index()
                api_obj.reset()
                run_tests(api_obj, remote)


class TestApiSearchBasics_nonP(TestApiSearchBasics):
        def setUp(self):
                self.debug_features = ["headers"]
                TestApiSearchBasics.setUp(self)

        def test_local_image_update(self):
                """Test that the index gets updated by image-update and
                that rebuilding the index works after updating the
                image. Specifically, this tests that rebuilding indexes with
                gaps in them works correctly."""
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                self._do_install(api_obj, ["example_pkg"])

                self.pkgsend_bulk(durl, self.example_pkg11)
                api_obj.refresh(immediate=True)

                self._do_image_update(api_obj)

                self._run_local_tests_example11_installed(api_obj)

                api_obj.rebuild_search_index()

                self._run_local_tests_example11_installed(api_obj)

        def test_bug_4048_1(self):
                """Checks whether the server deals with partial indexing."""
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                tmp_dir = os.path.join(depotpath, "index", "TMP")
                os.mkdir(tmp_dir)
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self._run_remote_empty_tests(api_obj)
                os.rmdir(tmp_dir)
                offset = 2
                depot_logfile = os.path.join(self.test_root,
                    "depot_logfile%d" % offset)
                tmp_dc = self.start_depot(12000 + offset, depotpath,
                    depot_logfile, refresh_index=True)
                time.sleep(1)
                # This should do something other than sleep for 1 sec
                self._run_remote_tests(api_obj)
                tmp_dc.kill()

        def test_bug_4048_2(self):
                """Checks whether the server deals with partial indexing."""
                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                tmp_dir = os.path.join(depotpath, "index", "TMP")
                os.mkdir(tmp_dir)
                self.pkgsend_bulk(durl, self.space_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self._run_remote_empty_tests(api_obj)
                os.rmdir(tmp_dir)
                self.pkgsend_bulk(durl, self.example_pkg10)
                time.sleep(1)
                self._run_remote_tests(api_obj)
                self._search_op(api_obj, True, "unique_dir",
                    self.res_space_unique)
                self._search_op(api_obj, True, "with*",
                    self.res_space_with_star)

        def test_bug_6177(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.pkgsend_bulk(durl, self.example_pkg11)
                self.pkgsend_bulk(durl, self.incorp_pkg10)
                self.pkgsend_bulk(durl, self.incorp_pkg11)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                res_both_actions = set([
                    ('pkg:/example_pkg@1.1-0', 'path',
                        'dir group=bin mode=0755 owner=root path=bin'),
                    ('pkg:/example_pkg@1.0-0', 'path',
                        'dir group=bin mode=0755 owner=root path=bin')
                ])

                res_10_action = set([
                    ('pkg:/example_pkg@1.0-0', 'path',
                        'dir group=bin mode=0755 owner=root path=bin')
                ])

                res_11_action = set([
                    ('pkg:/example_pkg@1.1-0', 'path',
                        'dir group=bin mode=0755 owner=root path=bin')
                ])

                res_both_packages = set([
                    "pkg:/example_pkg@1.1-0",
                    "pkg:/example_pkg@1.0-0"
                ])

                res_10_package = set([
                    "pkg:/example_pkg@1.0-0"
                ])

                res_11_package = set([
                    "pkg:/example_pkg@1.1-0"
                ])

                self._search_op(api_obj, True, "/bin", res_both_actions)

                # Test that if a package is installed, its version and newer
                # versions are shown.
                self._do_install(api_obj, ["example_pkg@1.0"])
                self._search_op(api_obj, True, "/bin", res_both_actions)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)

                # Check that after uninstall, back to returning all versions.
                self._do_uninstall(api_obj, ["example_pkg"])
                self._search_op(api_obj, True, "/bin", res_both_actions)
                self._search_op(api_obj, True, "/bin", res_both_packages,
                    return_actions=False)

                # Test that if a package is installed, its version and newer
                # versions are shown.  Older versions should not be shown.
                self._do_install(api_obj, ["example_pkg@1.1"])
                self._search_op(api_obj, True, "/bin", res_11_action)
                self._search_op(api_obj, True, "</bin>", res_11_package,
                    return_actions=False)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)
                self._search_op(api_obj, True, "</bin>", res_both_packages,
                    return_actions=False, prune_versions=False)
                
                # Check that after uninstall, back to returning all versions.
                self._do_uninstall(api_obj, ["example_pkg"])
                self._search_op(api_obj, True, "/bin", res_both_actions)

                # Check that only the incorporated package is returned.
                self._do_install(api_obj, ["incorp_pkg@1.0"])
                self._search_op(api_obj, True, "/bin", res_10_action)
                self._search_op(api_obj, True, "/bin", res_10_package,
                    return_actions=False)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)
                self._search_op(api_obj, True, "/bin", res_both_packages,
                    return_actions=False, prune_versions=False)

                # Should now show the 1.1 version of example_pkg since the
                # version has been upgraded.
                self._do_install(api_obj, ["incorp_pkg"])
                self._search_op(api_obj, True, "/bin", res_11_action)
                self._search_op(api_obj, True, "</bin>", res_11_package,
                    return_actions=False)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)
                self._search_op(api_obj, True, "</bin>", res_both_packages,
                    return_actions=False, prune_versions=False)

                # Should now show both again since the incorporation has been
                # removed.
                self._do_uninstall(api_obj, ["incorp_pkg"])
                self._search_op(api_obj, True, "/bin", res_both_actions)

                # Check that installed and incorporated work correctly together.
                self._do_install(api_obj, ["incorp_pkg@1.0", "example_pkg@1.0"])
                self._search_op(api_obj, True, "/bin", res_10_action)
                self._search_op(api_obj, True, "</bin>", res_10_package,
                    return_actions=False)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)
                self._search_op(api_obj, True, "</bin>", res_both_packages,
                    return_actions=False, prune_versions=False)

                # And that it works after the incorporation has been changed.
                self._do_install(api_obj, ["incorp_pkg"])
                self._search_op(api_obj, True, "/bin", res_11_action)
                self._search_op(api_obj, True, "</bin>", res_11_package,
                    return_actions=False)
                self._search_op(api_obj, True, "/bin", res_both_actions,
                    prune_versions=False)
                self._search_op(api_obj, True, "</bin>", res_both_packages,
                    return_actions=False, prune_versions=False)

        def __corrupt_depot(self, ind_dir):
                self.dc.stop()
                if os.path.exists(os.path.join(ind_dir, ss.MAIN_FILE)):
                        shutil.move(os.path.join(ind_dir, ss.MAIN_FILE),
                            os.path.join(ind_dir, "main_dict.ascii.v1"))
                self.dc.start()

        def __wait_for_indexing(self, d):
                init_time = time.time()
                there = True
                while there and ((time.time() - init_time) < 10):
                        there = os.path.exists(d)
                self.assert_(not there)
                time.sleep(1)

        def test_bug_7358_1(self):
                """Move files so that an inconsistent index is created and
                check that the server rebuilds the index when possible, and
                doesn't stack trace when it can't write to the directory."""

                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                ind_dir = os.path.join(depotpath, "index")
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                # Check when depot is empty.
                self.__corrupt_depot(ind_dir)
                self.__wait_for_indexing(os.path.join(ind_dir, "TMP"))
                # Since the depot is empty, should return no results but
                # not error.
                self._search_op(api_obj, True, 'e*', set())

                self.pkgsend_bulk(durl, self.example_pkg10)
                self.__wait_for_indexing(os.path.join(ind_dir, "TMP"))

                # Check when depot contains a package.
                self.__corrupt_depot(ind_dir)
                self.__wait_for_indexing(os.path.join(ind_dir, "TMP"))
                self._run_remote_tests(api_obj)

        def test_bug_7358_2(self):
                """Does same check as 7358_1 except it checks for interactions
                with writable root."""

                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                ind_dir = os.path.join(depotpath, "index")
                shutil.rmtree(ind_dir)
                writable_root = os.path.join(self.test_root,
                    "writ_root")
                writ_dir = os.path.join(writable_root, "index")
                self.dc.set_writable_root(writable_root)

                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)

                # Check when depot is empty.
                self.__corrupt_depot(writ_dir)
                # Since the depot is empty, should return no results but
                # not error.
                self.assert_(not os.path.isdir(ind_dir))
                self.__wait_for_indexing(os.path.join(writ_dir, "TMP"))
                self._search_op(api_obj, True, 'e*', set())

                self.pkgsend_bulk(durl, self.example_pkg10)
                self.__wait_for_indexing(os.path.join(writ_dir, "TMP"))

                # Check when depot contains a package.
                self.__corrupt_depot(writ_dir)
                self.__wait_for_indexing(os.path.join(writ_dir, "TMP"))
                self.assert_(not os.path.isdir(ind_dir))
                self._run_remote_tests(api_obj)

        def test_bug_8318(self):
                durl = self.dc.get_depot_url()
                self.pkgsend_bulk(durl, self.example_pkg10)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                uuids = []
                for p in api_obj.img.gen_publishers():
                        uuids.append(p.client_uuid)

                self._search_op(api_obj, True, "example_path",
                    self.res_remote_path)
                self._search_op(api_obj, True, "example_path",
                    self.res_remote_path, servers=[{"origin": durl}])
                lfh = file(self.dc.get_logpath(), "rb")
                found = 0
                num_expected = 7
                for line in lfh:
                        if "X-IPKG-UUID:" in line:
                                tmp = line.split()
                                s_uuid = tmp[1]
                                if s_uuid not in uuids:
                                        raise RuntimeError("Uuid found:%s not "
                                            "found in list of possible "
                                            "uuids:%s" % (s_uuid, uuids))
                                found += 1
                if found != num_expected:
                        raise RuntimeError(("Found %s instances of a "
                            "client uuid, expected to find %s.") %
                            (found, num_expected))

        def test_bug_9729_1(self):
                """Test that installing more than
                indexer.MAX_ADDED_NUMBER_PACKAGES packages at a time doesn't
                cause any type of indexing error."""
                durl = self.dc.get_depot_url()
                pkg_list = []
                for i in range(0, indexer.MAX_ADDED_NUMBER_PACKAGES + 1):
                        self.pkgsend_bulk(durl,
                            "open pkg%s@1.0,5.11-0\nclose\n" % i)
                        pkg_list.append("pkg%s" % i)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                self._do_install(api_obj, pkg_list)

        def test_bug_9729_2(self):
                """Test that installing more than
                indexer.MAX_ADDED_NUMBER_PACKAGES packages one after another
                doesn't cause any type of indexing error."""
                def _remove_extra_info(v):
                        return v.split("-")[0]
                durl = self.dc.get_depot_url()
                pkg_list = []
                for i in range(0, indexer.MAX_ADDED_NUMBER_PACKAGES + 3):
                        self.pkgsend_bulk(durl,
                            "open pkg%s@1.0,5.11-0\nclose\n" % i)
                        pkg_list.append("pkg%s" % i)
                self.image_create(durl)
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)
                fast_add_loc = os.path.join(self._get_index_dirs()[0],
                    "fast_add.v1")
                fast_remove_loc = os.path.join(self._get_index_dirs()[0],
                    "fast_remove.v1")
                api_obj.rebuild_search_index()
                for p in pkg_list:
                        self._do_install(api_obj, [p])
                # Test for bug 11104. The fast_add.v1 file was not being updated
                # correctly by install or image update, it was growing with
                # each modification.
                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_add_loc)
                    )), self.fast_add_after_install)
                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_remove_loc)
                    )), self.fast_remove_after_install)
                # Now check that image update also handles fast_add
                # appropriately when a small number of packages have changed.
                for i in range(0, 2):
                        self.pkgsend_bulk(durl,
                            "open pkg%s@2.0,5.11-0\nclose\n" % i)
                        pkg_list.append("pkg%s" % i)
                api_obj.refresh(immediate=True)
                self._do_image_update(api_obj)
                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_add_loc)
                    )), self.fast_add_after_first_update)

                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_remove_loc)
                    )), self.fast_remove_after_first_update)
                # Now check that image update also handles fast_add
                # appropriately when a large number of packages have changed.
                for i in range(3, indexer.MAX_ADDED_NUMBER_PACKAGES + 3):
                        self.pkgsend_bulk(durl,
                            "open pkg%s@2.0,5.11-0\nclose\n" % i)
                        pkg_list.append("pkg%s" % i)
                api_obj.refresh(immediate=True)
                self._do_image_update(api_obj)
                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_add_loc)
                    )), self.fast_add_after_second_update)
                self._check(set((
                    _remove_extra_info(v)
                    for v in self._get_lines(fast_remove_loc)
                    )), self.fast_remove_after_second_update)

        def test_bug_13485(self):
                """Test that indexer.Indexer's check_for_updates function works
                as excepted. This needs to be a separate test because other
                tests are likely to conintue working while reindexing more
                frequently than they should."""

                durl = self.dc.get_depot_url()
                depotpath = self.dc.get_repodir()
                ind_dir = os.path.join(depotpath, "index")
                repo = srepo.Repository(repo_root=depotpath, read_only=True,
                    fork_allowed=False, refresh_index=False)

                # Check that an empty index works correctly.
                fmris = indexer.Indexer.check_for_updates(ind_dir, repo.catalog)
                self.assertEqual(set(), fmris)

                self.pkgsend_bulk(durl, self.example_pkg10)
                self.__wait_for_indexing(os.path.join(ind_dir, "TMP"))
                repo = srepo.Repository(repo_root=depotpath, fork_allowed=False)
                self.assertEqual(len(set(repo.catalog.fmris())), 1)
                # Check that after publishing one package, no packages need
                # indexing.
                fmris = indexer.Indexer.check_for_updates(ind_dir, repo.catalog)
                self.assertEqual(set(), fmris)
                
                back_dir = ind_dir + ".BACKUP"
                shutil.copytree(ind_dir, back_dir)
                self.pkgsend_bulk(durl, self.example_pkg10)
                repo = srepo.Repository(repo_root=depotpath, fork_allowed=False)
                self.assertEqual(len(set(repo.catalog.fmris())), 2)
                # Check that publishing a second package also works.
                fmris = indexer.Indexer.check_for_updates(ind_dir, repo.catalog)
                self.assertEqual(set(), fmris)

                # Check that a package that was publisher but not index is
                # reported.
                fmris = indexer.Indexer.check_for_updates(back_dir,
                    repo.catalog)
                self.assertEqual(len(fmris), 1)


class TestApiSearchMulti(pkg5unittest.ManyDepotTestCase):

        example_pkg10 = """
            open example_pkg@1.0,5.11-0
            add dir mode=0755 owner=root group=bin path=/bin/example_dir
            close """

        res_alternate_server_local = set([
            ('pkg:/example_pkg@1.0-0', 'test2/example_pkg',
            'set name=pkg.fmri value=pkg://test2/example_pkg@1.0,5.11-0:')
        ])

        def _do_install(self, api_obj, pkg_list, **kwargs):
                self.debug("install %s" % " ".join(pkg_list))
                api_obj.plan_install(pkg_list, **kwargs)
                self._do_finish(api_obj)

        def _do_uninstall(self, api_obj, pkg_list, **kwargs):
                self.debug("uninstall %s" % " ".join(pkg_list))
                api_obj.plan_uninstall(pkg_list, False, **kwargs)
                self._do_finish(api_obj)

        def _do_image_update(self, api_obj, **kwargs):
                self.debug("planning image-update")
                api_obj.plan_update_all(sys.argv[0], verbose=False, **kwargs)
                self._do_finish(api_obj)

        def _do_finish(self, api_obj):
                api_obj.prepare()
                api_obj.execute_plan()
                api_obj.reset()

        def setUp(self):
                pkg5unittest.ManyDepotTestCase.setUp(self, ["test1", "test2",
                    "test3"], debug_features=["headers"])

                self.durl1 = self.dcs[1].get_depot_url()
                self.durl2 = self.dcs[2].get_depot_url()
                self.durl3 = self.dcs[3].get_depot_url()
                self.pkgsend_bulk(self.durl2, self.example_pkg10)

                self.image_create(self.durl1, prefix="test1")
                self.pkg("set-publisher -O " + self.durl2 + " test2")

        def _check(self, proposed_answer, correct_answer):
                if correct_answer == proposed_answer:
                        return True
                else:
                        self.debug("Proposed Answer: " + str(proposed_answer))
                        self.debug("Correct Answer : " + str(correct_answer))
                        if isinstance(correct_answer, set) and \
                            isinstance(proposed_answer, set):
                                self.debug("Missing: " +
                                    str(correct_answer - proposed_answer))
                                self.debug("Extra  : " +
                                    str(proposed_answer - correct_answer))
                        self.assertEqual(correct_answer, proposed_answer)

        @staticmethod
        def _extract_action_from_res(it, err):
                res = []
                if err:
                        try:
                                for query_num, auth, (version, return_type,
                                    (pkg_name, piece, act)) in it:
                                        res.append((fmri.PkgFmri(str(
                                            pkg_name)).get_short_fmri(), piece,
                                            TestApiSearchBasics._replace_act(
                                            act)),)
                        except err, e:
                                return res
                        else:
                                raise RuntimeError(
                                    "Didn't get expected error:%s" % err)
                else:
                        return TestApiSearchBasics._extract_action_from_res(it)
                        

        def _search_op(self, api_obj, remote, token, test_value,
            case_sensitive=False, return_actions=True, num_to_return=None,
            start_point=None, servers=None, expected_err=None):
                search_func = api_obj.local_search
                query = api.Query(token, case_sensitive, return_actions,
                    num_to_return, start_point)
                if remote:
                        search_func = api_obj.remote_search
                        res = set(self._extract_action_from_res(
                            search_func([query], servers=servers),
                            expected_err))
                else:
                        res = set(TestApiSearchBasics._extract_action_from_res(
                            search_func([query])))
                self._check(set(res), test_value)

        def test_bug_2955(self):
                """See http://defect.opensolaris.org/bz/show_bug.cgi?id=2955"""
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: False, PKG_CLIENT_NAME)
                self._do_install(api_obj, ["example_pkg"])

                # Test for bug 10690 by checking whether the fmri names
                # for packages installed from the non-preferred publisher
                # are parsed correctly. Specifically, test whether the name
                # alone is searchable, as well as the publisher/name
                # combination.
                self._search_op(api_obj, False, "set::test2/example_pkg",
                    self.res_alternate_server_local)
                self._search_op(api_obj, False, "set::example_pkg",
                    self.res_alternate_server_local)
                self._search_op(api_obj, False, "set::test2/*",
                    self.res_alternate_server_local)
                api_obj.rebuild_search_index()
                self._search_op(api_obj, False, "set::test2/example_pkg",
                    self.res_alternate_server_local)
                self._search_op(api_obj, False, "set::example_pkg",
                    self.res_alternate_server_local)
                self._search_op(api_obj, False, "set::test2/*",
                    self.res_alternate_server_local)
                self._do_uninstall(api_obj, ["example_pkg"])

        def test_bug_8318(self):
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self._search_op(api_obj, True,
                    "this_should_not_match_any_token", set())
                self._search_op(api_obj, True, "example_path",
                    set(), servers=[{"origin": self.durl1}])
                self._search_op(api_obj, True, "example_path",
                    set(), servers=[{"origin": self.durl3}])
                num_expected = { 1: 6, 2: 5, 3: 0 }
                for d in range(1,(len(self.dcs) + 1)):
                        try:
                                pub = api_obj.img.get_publisher(
                                    origin=self.dcs[d].get_depot_url())
                                c_uuid = pub.client_uuid
                        except api_errors.UnknownPublisher:
                                c_uuid = None
                        lfh = file(self.dcs[d].get_logpath(), "rb")
                        found = 0
                        for line in lfh:
                                if "X-IPKG-UUID:" in line:
                                        tmp = line.split()
                                        s_uuid = tmp[1]
                                        if s_uuid != c_uuid:
                                                raise RuntimeError(
                                                    "Found uuid:%s doesn't "
                                                    "match expected uuid:%s, "
                                                    "d:%s, durl:%s" %
                                                    (s_uuid, c_uuid, d,
                                                    self.dcs[d].get_depot_url()))
                                        found += 1
                        if found != num_expected[d]:
                                raise RuntimeError("d:%s, found %s instances of"
                                    " a client uuid, expected to find %s." %
                                    (d, found, num_expected[d]))

        def test_bug_12739(self):
                progresstracker = progress.NullProgressTracker()
                api_obj = api.ImageInterface(self.get_img_path(), API_VERSION,
                    progresstracker, lambda x: True, PKG_CLIENT_NAME)

                self._search_op(api_obj, True, "example_dir",
                    set([("pkg:/example_pkg@1.0-0", "basename",
                        "dir group=bin mode=0755 owner=root "
                        "path=bin/example_dir")]))
                self.dcs[1].stop()
                self._search_op(api_obj, True, "example_dir",
                    set([("pkg:/example_pkg@1.0-0", "basename",
                        "dir group=bin mode=0755 owner=root "
                        "path=bin/example_dir")]),
                        expected_err=api_errors.ProblematicSearchServers)
                self.pkg("search example_dir", exit=3)
                
if __name__ == "__main__":
        unittest.main()
