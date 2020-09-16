""""UI Tab configuration for iOS app. This file stores the default configuration"""
from .models import UITab, PlanUITab, PlanUIMoreTab

# Default tabs (tabs must exist in database with these titles)
TAB_MORE = "More"
TAB_EXPLORE = "Explore"
TAB_EARN = "Earn"
TAB_SUBMIT = "Submit"
TAB_TRACK = "Track"
TAB_PROFILE = "Profile"
TAB_SITES = "Sites"
TAB_FEEDBACK = "Feedback"
TAB_TERMS = "Terms"
TAB_LOGOUT = "Logout"

DEFAULT_INDIV_SUBSCRIBER_TABS = (
    TAB_EXPLORE,
    TAB_EARN,
    TAB_SUBMIT,
    TAB_PROFILE,
    TAB_MORE
)

DEFAULT_ENTERPRISE_TABS = (
    TAB_EXPLORE,
    TAB_EARN,
    TAB_TRACK,
    TAB_SUBMIT,
    TAB_MORE
)

DEFAULT_MORE_ITEMS = (
    TAB_SITES,
    TAB_FEEDBACK,
    TAB_TERMS,
    TAB_LOGOUT
)

def addTabToMoreItems(moreTab, tabDict):
    items = moreTab['contents']['moreTab']['items']
    items.append(tabDict)

def makeTabConfigData(tab_titles, more_titles):
    """
    Args:
        tab_titles: list of tab titles
        more_titles: list of more_titles
    Returns: list of dicts - each dict is a tab.
    """
    data = []
    moreTab = None
    #print(tab_titles)
    #print(more_titles)
    tabsByTitle = UITab.objects.getTabsByTitles(tab_titles+more_titles)
    for index,title in enumerate(tab_titles):
        uitab = tabsByTitle[title] # UITab instance
        tabDict = uitab.toUIDict(index)
        if title == TAB_MORE:
            moreTab = tabDict
        data.append(tabDict)
    # add items to moreTab
    if moreTab:
        for index,title in enumerate(more_titles):
            uitab = tabsByTitle[title] # UITab instance
            tabDict = uitab.toUIDict(index)
            addTabToMoreItems(moreTab, tabDict) 
    return data


def getDefaultTabConfig():
    """Use default tab configuration
    Returns: list of dicts
    """
    tab_titles = DEFAULT_INDIV_SUBSCRIBER_TABS
    more_titles = DEFAULT_MORE_ITEMS
    return makeTabConfigData(tab_titles, more_titles)

def getPlanTabConfig(plan):
    """
    Args:
        plan: SubscriptionPlan instance
    1. Get the PlanUITabs for this plan order by index
       If plan does not have custome tabs: use default
    2. Get the PlanUIMoreTabs for this plan order by index
        If plan does not have custom more items: use default
    Returns: list of dicts
    """
    qs = PlanUITab.objects.filter(plan=plan).order_by('index')
    tab_titles = [m.tab.title for m in qs]
    if not tab_titles:
        # plan does not specify a custom config. Use default
        if plan.isEnterprise():
            tab_titles = DEFAULT_ENTERPRISE_TABS
        else:
            tab_titles = DEFAULT_INDIV_SUBSCRIBER_TABS
    qs_more = PlanUIMoreTab.objects.filter(plan=plan).order_by('index')
    more_titles = [m.tab.title for m in qs_more]
    if not more_titles and TAB_MORE in tab_titles:
        # Plan does not specify a custom, and moreTab is included in tabs
        more_titles = DEFAULT_MORE_ITEMS
    return makeTabConfigData(tab_titles, more_titles)
