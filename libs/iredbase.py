# Author: Zhang Huangbin <zhb@iredmail.org>

import os
import sys
import ConfigParser

import web
from jinja2 import Environment, FileSystemLoader

# Init settings

# Directory to be used as the Python egg cache directory.
# Note that the directory specified must exist and be writable by the
# user that the daemon process run as.
os.environ['PYTHON_EGG_CACHE'] = '/tmp/.iredadmin-eggs'
os.environ['LC_ALL'] = 'C'

# init settings.ini to a web.storage
rootdir = os.path.abspath(os.path.dirname(__file__)) + '/../'
iniSettings = ConfigParser.SafeConfigParser()
cfgfile = os.path.join(rootdir, 'settings.ini')
if os.path.exists(cfgfile):
    iniSettings.read(cfgfile)
else:
    sys.exit('Error: No config file found: %s.' % cfgfile)

iniSections = web.storage(iniSettings._sections)
cfg = web.iredconfig = web.storage()
for k in iniSections:
    web.iredconfig[k] = web.storage(iniSections[k])

web.iredconfig['rootdir'] = rootdir

webmaster = cfg.general.get('webmaster', 'root')
backend = cfg.general.get('backend', 'ldap')

# Set debug mode.
if cfg.general.get('debug', 'False').lower() in ['true', ]:
    web.config.debug = True
else:
    web.config.debug = False

# Initialize object which used to stored all translations.
cfg.allTranslations = web.storage()

# Get global language setting.
lang = cfg.general.get('lang', 'en_US')

import iredutils
import settings
from ireddate import convert_utc_to_timezone

#####################################
# Store all 'true/false' in session.
#
# Get value of 'show_used_quota' in [general].
enableShowUsedQuota = False
if backend in ['mysql', 'dbmail_mysql']:
    enableShowUsedQuota = True
else:
    if cfg.general.get('show_used_quota', 'False').lower() in ['true', ]:
        enableShowUsedQuota = True

# Get value of 'enabled' in [policyd].
enablePolicyd = False
if cfg.policyd.get('enabled', 'False').lower() in ['true', ]:
    enablePolicyd = True

# Get value of 'quarantine' in [amavisd].
enableAmavisdQuarantine = False
enableAmavisdLoggingIntoSQL = False
if cfg.amavisd.get('quarantine', 'False').lower() in ['true', ]:
    enableAmavisdQuarantine = True

# Get value of 'logging_into_sql' in [amavisd].
if cfg.amavisd.get('logging_into_sql', 'False').lower() in ['true', ]:
    enableAmavisdLoggingIntoSQL = True

# Set session parameters.
web.config.session_parameters['cookie_name'] = 'iRedAdmin-Pro'
web.config.session_parameters['cookie_domain'] = None
web.config.session_parameters['ignore_expiry'] = False
web.config.session_parameters['ignore_change_ip'] = False

# Initialize session object.
session_dbn = 'mysql'
if backend in ['pgsql', ]:
    session_dbn = 'postgres'

db_iredadmin = web.database(
    host=cfg.iredadmin.get('host', 'localhost'),
    port=int(cfg.iredadmin.get('port', '3306')),
    dbn=session_dbn,
    db=cfg.iredadmin.get('db', 'iredadmin'),
    user=cfg.iredadmin.get('user', 'iredadmin'),
    pw=cfg.iredadmin.get('passwd'),
)

# Store session data in 'iredadmin.sessions'.
sessionStore = web.session.DBStore(db_iredadmin, 'sessions')

# We will use web.admindb in module 'iredutils' later.
web.admindb = db_iredadmin

# URL handlers.
# Import backend related urls.
if backend == 'ldap':
    from controllers.ldap.urls import urls as backendUrls
elif backend == 'mysql':
    from controllers.mysql.urls import urls as backendUrls
elif backend == 'pgsql':
    from controllers.pgsql.urls import urls as backendUrls
elif backend == 'dbmail_mysql':
    from controllers.dbmail_mysql.urls import urls as backendUrls
else:
    backendUrls = []

urls = backendUrls

# Import policyd related urls.
if enablePolicyd is True:
    from controllers.policyd.urls import urls as policydUrls
    urls += policydUrls

# Import amavisd related urls.
if enableAmavisdQuarantine or enableAmavisdLoggingIntoSQL:
    from controllers.amavisd.urls import urls as amavisdUrls
    urls += amavisdUrls

from controllers.panel.urls import urls as panelUrls
urls += panelUrls

# Initialize application object.
app = web.application(urls, globals(),)

session = web.session.Session(
    app,
    sessionStore,
    initializer={
        'webmaster': webmaster,
        'username': None,
        'logged': False,
        'failedTimes': 0,   # Integer.
        'lang': lang,

        # Store password in plain text.
        'storePasswordInPlain': settings.STORE_PASSWORD_IN_PLAIN,

        # Show used quota.
        'enableShowUsedQuota': enableShowUsedQuota,

        # Enable Policyd & Amavisd integration.
        'enablePolicyd': enablePolicyd,

        # Amavisd related features.
        'enableAmavisdQuarantine': enableAmavisdQuarantine,
        'enableAmavisdLoggingIntoSQL': enableAmavisdLoggingIntoSQL,
    }
)

web.config._session = session


# Generate CSRF token and store it in session.
def csrf_token():
    if not 'csrf_token' in session.keys():
        session['csrf_token'] = iredutils.getRandomPassword(32)

    return session['csrf_token']


# Hooks.
def hook_lang():
    web.ctx.lang = web.input(lang=None, _method="GET").lang or session.get('lang', 'en_US')


# Define template render.
def render_template(template_name, **context):
    jinja_env = Environment(
        loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), '../templates/default', )),
        extensions=[],
    )
    jinja_env.globals.update({
        '_': iredutils.iredGettext,    # Override _() which provided by Jinja2.
        'ctx': web.ctx,                 # Used to get 'homepath'.
        'skin': 'default',              # Used for static files.
        'session': web.config._session,
        'backend': backend,
        'csrf_token': csrf_token,
        'pageSizeLimit': settings.PAGE_SIZE_LIMIT,
        'priorityOfUserThrottling': settings.PRIORITY_OF_USER_THROTTLING,
        'priorityOfDomainThrottling': settings.PRIORITY_OF_DOMAIN_THROTTLING,
        'priorityOfOverrideThrottling': settings.PRIORITY_OF_OVERRIDE_THROTTLING,
    })

    jinja_env.filters.update({
        'filesizeformat': iredutils.filesizeformat,
        'setDatetimeFormat': iredutils.setDatetimeFormat,
        'getRandomPassword': iredutils.getRandomPassword,
        'getPercentage': iredutils.getPercentage,
        'cutString': iredutils.cutString,
        'convert_utc_to_timezone': convert_utc_to_timezone,
    })

    return jinja_env.get_template(template_name).render(context)


class sessionExpired(web.HTTPError):
    def __init__(self, message):
        message = web.seeother('/login?msg=SESSION_EXPIRED')
        web.HTTPError.__init__(self, '303 See Other', {}, data=message)


# Logger. Logging into SQL database.
def logIntoSQL(msg, admin='', domain='', username='', event='', loglevel='info',):
    try:
        if admin == '':
            admin = session.get('username', '')

        db_iredadmin.insert(
            'log',
            admin=str(admin),
            domain=str(domain),
            username=str(username),
            loglevel=str(loglevel),
            event=str(event),
            msg=str(msg),
            ip=str(session.ip),
        )
    except Exception, e:
        pass


# Log error message. default log to sys.stderr.
def logError(*args):
    for s in args:
        try:
            print >> sys.stderr, web.safestr(s)
        except Exception, e:
            print >> sys.stderr, e

app.add_processor(web.loadhook(hook_lang))

# Mail 500 error to webmaster.
if cfg.general.get('mail_error_to_webmaster', 'False').lower() == 'true':
    app.internalerror = web.emailerrors(webmaster, web.webapi._InternalError,)

# Store objects in 'web' module.
web.app = app
web.render = render_template
web.logger = logIntoSQL
web.logError = logError
web.session.SessionExpired = sessionExpired
