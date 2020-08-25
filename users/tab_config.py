""""Temporary file for tab config until we have a db schema in place"""
from copy import deepcopy

TAB_EXPLORE = {
  "index": 0,
  "title": "Explore",
  "icon": {
    "at1x": "/assets/images/ios/explore-icon/explore-icon.png",
    "at2x": "/assets/images/ios/explore-icon/explore-icon@2x.png",
    "at3x": "/assets/images/ios/explore-icon/explore-icon@3x.png"
  },
  "contents": {
    "exploreTab": {
      "homeURL": "/submit"
    }
  }
}

TAB_EARN = {
  "index": 1,
  "title": "Earn",
  "icon": {
    "at1x": "/assets/images/ios/earn-icon/earn-icon.png",
    "at2x": "/assets/images/ios/earn-icon/earn-icon@2x.png",
    "at3x": "/assets/images/ios/earn-icon/earn-icon@3x.png"
  },
  "contents": {
    "webview": {
      "url": "/feed"
    }
  }
}

TAB_SUBMIT = {
  "index": 2,
  "title": "Submit",
  "icon": {
    "at1x": "/assets/images-ios/submit-icon/submit-icon.png",
    "at2x": "/assets/images-ios/submit-icon/submit-icon@2x.png",
    "at3x": "/assets/images-ios/submit-icon/submit-icon@3x.png"
  },
  "contents": {
    "webview": {
      "url": "/dashboard"
    } 
  }
}

TAB_PROFILE = {
  "index": 3,
  "title": "Profile",
  "icon": {
    "at1x": "/assets/images/ios/profile-icon/profile-icon.png",
    "at2x": "/assets/images/ios/profile-icon/profile-icon@2x.png",
    "at3x": "/assets/images/ios/profile-icon/profile-icon@3x.png"
  },
  "contents": {
    "webview": {
      "url": "/profile"
    } 
  }
}

TAB_SITES = {
    "index": 0,
    "title": "Sites",
    "icon": {
        "at1x": "/assets/images/ios/explore-icon/explore-icon.png",
        "at2x": "/assets/images/ios/explore-icon/explore-icon@2x.png",
        "at3x": "/assets/images/ios/explore-icon/explore-icon@3x.png"
    },
    "contents": {
        "webview": {
            "url": "/whitelist"
        } 
    }
}

TAB_FEEDBACK = {
    "index": 1,
    "title": "Feedback",
    "icon": {
        "at1x": "/assets/images/ios/explore-icon/feedback-icon.png",
        "at2x": "/assets/images/ios/explore-icon/feedback-icon@2x.png",
        "at3x": "/assets/images/ios/explore-icon/feedback-icon@3x.png"
    },
    "contents": {
        "webview": {
            "url": "/feedback"
        } 
    }
}

TAB_TERMS = {
    "index": 2,
    "title": "Terms",
    "icon": {
        "at1x": "/assets/images/ios/terms-icon/terms-icon.png",
        "at2x": "/assets/images/ios/terms-icon/terms-icon@2x.png",
        "at3x": "/assets/images/ios/terms-icon/terms-icon@3x.png"
    },
    "contents": {
        "webview": {
            "url": "/terms.html"
        } 
    }
}

TAB_LOGOUT = {
    "index": 3,
    "title": "Logout",
    "icon": {
        "at1x": "/assets/images/ios/logout-icon/logout-icon.png",
        "at2x": "/assets/images/ios/logout-icon/logout-icon@2x.png",
        "at3x": "/assets/images/ios/logout-icon/logout-icon@3x.png"
    },
    "contents": {
        "logout": {}
    }
}

TAB_MORE = {
  "index": 4,
  "title": "More",
  "icon": {
    "at1x": "/assets/images/ios/more-icon/more-icon.png",
    "at2x": "/assets/images/ios/more-icon/more-icon@2x.png",
    "at3x": "/assets/images/ios/more-icon/more-icon@3x.png"
  },
  "contents": {
    "moreTab": {
      "items": []
    } 
  }
}

TABS_BY_NAME = {
    'explore': TAB_EXPLORE,
    'earn': TAB_EARN,
    'submit': TAB_SUBMIT,
    'profile': TAB_PROFILE,
    'more': TAB_MORE,
    'sites': TAB_SITES,
    'feedback': TAB_FEEDBACK,
    'terms': TAB_TERMS,
    'logout': TAB_LOGOUT
}

def getTab(name):
    return deepcopy(TABS_BY_NAME[name])

def addTabToMoreItems(moreTab, tabDict):
    items = moreTab['contents']['moreTab']['items']
    num_items = len(items)
    tabDict['index'] = num_items
    items.append(tabDict)

def addTabToData(data, tabDict):
    """Append tabDict to data and set tabDict.index
    Example data: [
            exploreTab,
            earnTab,
            submitTab,
            profileTab,
            moreTab
        ]
    """
    num_tabs = len(data)
    tabDict['index'] = num_tabs
    data.append(tabDict)
