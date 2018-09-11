from setuptools import find_packages, setup

setup(
    name='manibot',
    version='1.0.0b',
    description='A Discord bot for the Hatigarm Community.',
    url='https://github.com/scragly/Manibot',
    author='Scragly',
    license='GNU General Public License v3.0',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Topic :: Communications :: Chat',
        'Topic :: Utilities',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3.6',
    ],

    keywords='community discord bot hatigarm scans',

    # find_packages(exclude=['contrib', 'docs', 'tests'])
    packages=find_packages(),

    install_requires=[
        'discord.py',
        'python-dateutil>=2.6',
        'asyncpg>=0.13',
        'python-Levenshtein>=0.12',
        'fuzzywuzzy',
        'psutil',
        'aiocontextvars',
        'colorthief',
        'more_itertools',
        'bs4',
        'feedparser',
        'pytz',
        'pendulum'
    ],

    dependency_links=[
        'git+https://github.com/Rapptz/discord.py@rewrite#egg=discord.py-1'
    ],

    package_data={
        'manibot': ['data/*.json'],
    },

    entry_points={
        'console_scripts': [
            'manibot=manibot.launcher:main',
            'manibot-bot=manibot.__main__:main'
        ],
    },
)
