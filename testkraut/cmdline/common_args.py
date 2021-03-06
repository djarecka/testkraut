# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

# argument spec template
#<name> = (
#    <id_as_positional>, <id_as_option>
#    {<ArgusmentParser.add_arguments_kwargs>}
#)

from ..utils import get_filecache_dir
from ..cmdline.helpers import HelpAction

help = (
    'help', ('-h', '--help', '--help-np'),
    dict(nargs=0, action=HelpAction,
         help="""show this help message and exit. --help-np forcefully disables
                 the use of a pager for displaying the help.""")
)

version = (
    'version', ('--version',),
    dict(action='version',
         help="show program's version and license information and exit")
)


filecache = (
    'filecache', ('-c', '--filecache'),
    dict(default=get_filecache_dir(),
         help="""path to the file cache. By default the cache is located
              at ~/.cache/testkraut/files. A XDG_CACHE_HOME variable
              will also be honored when determining the default.""")
)

librarypaths = (
    'library', ('-l', '--library'),
    dict(action='append', default=[],
         help="""path to an additional test library. This path is added to the
              configured list of libraries and to the default search paths.""")
)

specoutput = (
    'output-spec', ('-o', '--output-spec'),
    dict(metavar='FILENAME', dest='ospec_filename',
         help="""file name of the output SPEC file""")
)

include_spec_elements = (
    'include-elements', ('-i', '--include-elements'),
    dict(action='append',
         help="""if provided, only differences of elements whos
              location matching any of the given regular expressions
              regular expressions are reported. The option can be
              given multiple times. Include expressions are applied
              before any potential exclude expressions
              (see --exclude_elements)."""),
)

exclude_spec_elements = (
    'exclude-elements', ('-e', '--exclude-elements'),
    dict(action='append',
         help="""if provided, differences of elements whos
              location matching any of the given regular expressions
              regular expressions are NOT reported. The option can be
              given multiple times. Exclude expressions are applied
              after any potential include expressions
              (see --include_elements)."""),
)


