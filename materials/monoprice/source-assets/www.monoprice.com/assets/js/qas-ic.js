/*global window, console, $, LANGUAGES, alert */
/** @namespace Namespace for On Demand implementation codes. */
var qas = qas || {};
/** @namespace Namespace for search configuration and classes. */
qas.search = qas.search || {};
/** @namespace Namespace for language configuration and classes. */
qas.lang = qas.lang || {};
/** @namespace Namespace for utility functions and classes. */
qas.util = qas.util || {};
/** @namespace Namespace for user interface functions and classes. */
qas.ui = qas.ui || {};
/** @class The type of languages available. The value of each type must be the same as the filename of language file. */
qas.lang.Type = {
	/** @static */
	EN_US : "en-us"
};
/** @class The value displayed in the language combobox for each languages. */
qas.lang.DisplayMapping = {
	/** @static */
	EN_US : "English (US)"
};
/**
 * Cookie name for language
 * @type {string}
 * @default "lang"
 */
qas.lang.COOKIE_NAME = "lang";
/**
 * Language directory
 * @type {string}
 * @default "js/lang/"
 */
qas.lang.LANGUAGE_DIRECTORY = "/assets/js/lang/";
/**
 * Language file extension
 * @type {string}
 * @default ".js"
 */
qas.lang.LANGUAGE_FILE_EXTENSION = ".js";
/**
 * JQuery Selector for language span
 * @type {string}
 * @default "span.translation"
 */
qas.lang.LANGUAGE_SPAN = "span.translation";
/**
 * Default language to be displayed
 * @type {qas.lang.Type}
 * @default qas.lang.Type.EN_UK
 */
qas.lang.DEFAULT_LANGUAGE = qas.lang.Type.EN_US;
/**
 * Default header string to be displayed
 * @type {string}
 * @default JSP
 */
qas.lang.PROGRAMMING_LANGUAGE = "C# .NET";
/**
 * JQuery Selector for button
 * @type {string}
 * @default "input#translation"
 */
qas.lang.BUTTON = "input.translation";

/** @class The type of search engines. */
qas.search.EngineType = {
	/** @static */
	SINGLELINE : "Singleline",
	/** @static */
	TYPEDOWN : "Typedown",
	/** @static */
	VERIFICATION : "Verification",
	/** @static */
	KEYFINDER : "Keyfinder",
	/** @static */
	INTUITIVE : "Intuitive"
};
/** @class The type of search intensities. */
qas.search.IntensityType = {
	/** @static */
	EXACT : "Exact",
	/** @static */
	CLOSE : "Close",
	/** @static */
	EXTENSIVE : "Extensive"
};
/** @class The type of promptsets. */
qas.search.PromptsetType = {
	/** Oneline @static */
	ONELINE : "OneLine",
	/** @static */
	DEFAULT : "Default",
	/** @static */
	GENERIC : "Generic",
	/** @static */
	OPTIMAL : "Optimal",
	/** @static */
	ALTERNATE : "Alternate",
	/** @static */
	ALTERNATE2 : "Alternate2",
	/** @static */
	ALTERNATE3 : "Alternate3"
};
/** @class Type of DPV statuses. */
qas.search.DPVStatus = {
	/** @static */
	CONFIGURED : "DPVNotConfigured",
	/** @static */
	CONFIRMED : "DPVConfirmed",
	/** @static */
	CONFIRMED_MISSING_SEC : "DPVConfirmedMissingSec",
	/** @static */
	NOT_CONFIRMED : "DPVNotConfirmed",
	/** @static */
	LOCKED : "DPVLocked",
	/** @static */
	SEED_HIT : "DPVSeedHit"
};
/**
 * Default URL of REST API.
 * @type {string}
 * @default "QASCaptureController"
 */
qas.search.DEFAULT_AJAX_URL = "/qas/QasCaptureController";
/**
 * Default AJAX invocation.
 * @type {bool}
 * @default true
 */
qas.search.DEFAULT_AJAX_IS_ASYNC = true;
/**
 * Default datatype. DO NOT CHANGE TO ANYTHING OTHER THAN JSON unless rest controller is changed to support.
 * @type {string}
 * @default "json"
 */
qas.search.DEFAULT_AJAX_DATA_TYPE = "json";
/**
 * Default invoke api timeout. When timeout, errorcallback will be invoked.
 * @type {number}
 * @default 5000
 */
qas.search.DEFAULT_AJAX_TIMEOUT = 10000;
/**
 * Default country ID (datamap ID) for all APIs. Available country ID can be obtained by invoking QASCapture.getAllDataSet()
 * @type {string}
 * @default "GBR";
 */
qas.search.DEFAULT_COUNTRY_ID = "USA";
/**
 * Default layout to use for a specfic country.
 */
qas.search.DEFAULT_COUNTRY_LAYOUT_MAP = {
    "GBR": "Database Layout",
	"USA": "Monoprice_Prod_RDI",
	"CAN": "Monoprice_Prod_RDI",
    "AUS": "Database Layout",
    "NZL": "Database Layout",
    "FRP": "Database Layout"
};
/**
 * Default layout for all APIs. Available layouts can be obtained by invoking
 * QASCapture.getAllLayout();
 * @type {string}
 * @default "Database Layout".
 */
qas.search.DEFAULT_LAYOUT = "Database Layout";
/**
 * Default search engine type for all APIs.
 * @type {string}
 * @default qas.search.EngineType.SINGLELINE
 */
qas.search.DEFAULT_ENGINE = qas.search.EngineType.VERIFICATION;
/**
 * Default promptset for all API.
 * @type {string}
 * @default qas.search.PromptsetType.DEFAULT
 */
qas.search.DEFAULT_PROMPTSET_TYPE = qas.search.PromptsetType.DEFAULT;
/**
 * Default flatten flag for all API.
 * @type {boolean}
 * @default false
 */
qas.search.DEFAULT_IS_FLATTEN = false;
/**
 * Default threshold for all API. This is the number of items to be displayed when calling refine() api, usually displayed in picklist.
 * @type {number}
 * @default 25
 */
qas.search.DEFAULT_THRESHOLD = 25;
/**
 * Default timeout when invoking refine() API. This is the timeout when calling refine() api.
 * @type {number}
 * @default 5000
 */
qas.search.DEFAULT_TIMEOUT = 5000;
/**
 * Default search intensity when invoking all API.
 * @type {string}
 * @default qas.search.IntensityType.CLOSE
 */
qas.search.DEFAULT_INTENSITY = qas.search.IntensityType.CLOSE;
/**
 * Default localisation. (Currently not implemented in OnDemand server)
 * @type {string}
 * @default ""
 */
qas.search.DEFAULT_LOCALISATION = "";
/**
 * Default request tag.
 * @type {string}
 * @default ""
 */
qas.search.DEFAULT_REQUEST_TAG = "";
/**
 * Default flag to indicate is formatted address in picklist.
 * @type {boolean}
 * @default false
 */
qas.search.DEFAULT_IS_FORMATTED_ADDRESS_IN_PICKLIST = false;
/**
 * Default country cookie expiry (in days).
 * @default 1
 */
qas.search.DEFAULT_COUNTRY_COOKIE_EXPIRY = 1;
/**
 * Default country cookie key.
 * @default "qas.search.country"
 */
qas.search.DEFAULT_COUNTRY_COOKIE_NAME = "qas.search.country";
/**
 * Default search delimiter.
 * @default "|"
 */
qas.search.DEFAULT_DELIMITER = "|";
/**
 * display any errors encountered in an alert, should only be used for debugging
 * @default true
 */
qas.search.DISPLAY_ERROR = false;
/**
 * Dictionary of available countries. Values are populated by QASCapture object and will be reused once populated.
 */
qas.search.AvailableCountries = null;
qas.search.ALL_COUNTRIES = [{
	"Name" : "Canada",
	"ID" : "CAN"
}, {
	"Name" : "United States",
	"ID" : "USA"
}];
/**
 * Checks if an object is an element in the array.
 * http://stackoverflow.com/questions/237104/javascript-array-containsobj
 */
qas.util.checkIsInArray = function (arr, obj) {
	var i = 0, iLen = arr.length;
	// http://stackoverflow.com/questions/3000276/the-unexpected-error-in-jslint
	for(; i < iLen; i += 1) {
		if(arr[i] === obj) {
			return true;
		}
	}
	return false;
};
/**
 * Log to the window console if available.
 */
qas.util.log = function () {
	if(window.console) {
		window.console.log(arguments);
	}
};
// ascending order
qas.util.CompareById = function (x, y) {
	return x.ID - y.ID;
};
qas.util.CompareByName = function (x, y) {
	return ((x.Name === y.Name) ? 0 : ((x.Name > y.Name) ? 1 : -1 ));
};
//qas.ui.Datamap = function (captureObj) {
//	var capture = captureObj || new qas.search.QASCapture();
//	var defaultCountries = qas.search.ALL_COUNTRIES;

//	var getCountryInDefault = function () {
//		return qas.search.DEFAULT_COUNTRY_ID;
//	};
//	var getCountryInCookie = function (countryControlId) {
//		var cookieName = qas.search.DEFAULT_COUNTRY_COOKIE_NAME;
//		if(countryControlId !== null && countryControlId !== "") {
//			cookieName = cookieName + "#" + countryControlId;
//		}
//		return $.cookie(cookieName);
//	};
//	var setCountryInCookie = function (countryId, countryControlId) {
//		var cookieName = qas.search.DEFAULT_COUNTRY_COOKIE_NAME;
//		if(countryControlId !== null && countryControlId !== "") {
//			cookieName = cookieName + "#" + countryControlId;
//		}
//		$.cookie(cookieName, countryId, qas.search.DEFAULT_COUNTRY_COOKIE_EXPIRY);
//	};
//	var getFirstCountry = function (availableCountries, defaultCountries) {
//		// the first country to be returned
//		var firstCountry = null;
//		// find the first country in available countries array
//		var i = 0, iLen = availableCountries.length;
//		for(; i < iLen; i++) {
//			// if already found the first country, stop searching
//			if(firstCountry !== null) {
//				break;
//			}
//			firstCountry = availableCountries[i].ID;
//		}
//		// find the first country in default countries array
//		var j = 0, jLen = defaultCountries.length;
//		for(; j < jLen; j++) {
//			// if already found the first country, stop searching
//			if(firstCountry !== null) {
//				break;
//			}
//			firstCountry = defaultCountries[i].ID;
//		}
//		return firstCountry;
//	};
//	var checkIsInCountryList = function (countryId, countries) {
//		var isInCountryList = false;
//		if( typeof countries !== "undefined" && countries !== null) {
//			var i = 0, iLen = countries.length;
//			for(; i < iLen; i++) {
//				if(countries[i].ID === countryId) {
//					isInCountryList = true;
//				}
//			}
//		}
//		return isInCountryList;
//	};
//	var getCountryName = function (countryId, countries) {
//	    var countryName = null;
//        if( typeof countries !== "undefined" && countries !== null) {
//            var i = 0, iLen = countries.length;
//            for(; i < iLen; i++) {
//                if(countries[i].ID === countryId) {
//                    countryName = countries[i].Name
//                    break;
//                }
//            }
//        }
//        return countryName;
//	};
//	var autoSelectCountry = function (countryControl, availableCountries) {
//		var jqCountryControl = $(countryControl);
//		// get cookie
//		var selectedCountry = getCountryInCookie(jqCountryControl.attr("id"));
//		// if cookie country is empty, get default and set cookie
//		if(selectedCountry === null || (!checkIsInCountryList(selectedCountry, availableCountries) && !checkIsInCountryList(selectedCountry, defaultCountries))) {
//			selectedCountry = getCountryInDefault();
//			setCountryInCookie(selectedCountry, jqCountryControl.attr("id"));
//		}
//		// if selected country not in the list of available countries, select the first available country
//		if(!checkIsInCountryList(selectedCountry, availableCountries) && !checkIsInCountryList(selectedCountry, defaultCountries)) {
//			selectedCountry = getFirstCountry(availableCountries, defaultCountries);
//		}
//		// try to select (if fail, do nothing)
//		if(selectedCountry !== null) {
//			jqCountryControl.val(selectedCountry);
//			capture.setCountryId(selectedCountry);
//            capture.setCountryName(getCountryName(selectedCountry));
//		}
//	};
//	var populateCountryControlWithData = function (countryControl, availableCountries, defaultCountries) {
//		var jqCountryControl = $(countryControl);
//		jqCountryControl.empty();
//		// populate values from dataset
//		if(null !== availableCountries) {
//			// Sort the array
//			availableCountries.sort(qas.util.CompareByName);
//			// Datamap available
//			jqCountryControl.append("<option value='' class='heading'>-- --  Select your country -- --</option>");
//			$.each(availableCountries, function (key, value) {
//				jqCountryControl.append("<option value ='" + value.ID + "'>" + value.Name + "</option>");
//			});
//			// Other datamap
//			jqCountryControl.append("<option value='' class='heading'>-- Other --</option>");
//		}
//		// Add datamap which is not duplicated
//		$.each(defaultCountries, function (key, value) {
//			var duplicate = false;

//			// if there's available countries, the default country should not already been added in the available countries
//			if(null !== availableCountries) {
//				var i = 0;
//				var iLen = availableCountries.length;
//				for(; i < iLen; i++) {
//					if(value.ID === availableCountries[i].ID || value.Name === availableCountries[i].Name) {
//						duplicate = true;
//						break;
//					}
//				}
//			}

//			if(!duplicate) {
//				jqCountryControl.append("<option value ='" + value.ID + "'>" + value.Name + "</option>");
//			}
//		});
//	};
//	var autoselectCountryControl = function (countryControl, isControlSpecific, availableCountries, defaultCountries) {
//		var jqCountryControl = $(countryControl);
//		var controlId = isControlSpecific ? jqCountryControl.attr("id") : "";
//		var selectedCountry = getCountryInCookie(controlId);
//		// if cookie country is empty, get default and set cookie
//		if(selectedCountry === null || (!checkIsInCountryList(selectedCountry, availableCountries) && !checkIsInCountryList(selectedCountry, defaultCountries))) {
//			selectedCountry = getCountryInDefault();
//			setCountryInCookie(selectedCountry, controlId);
//		}
//		// if selected country not in the list of available countries, select the first available country
//		if(!checkIsInCountryList(selectedCountry, availableCountries) && !checkIsInCountryList(selectedCountry, defaultCountries)) {
//			selectedCountry = getFirstCountry(availableCountries, defaultCountries);
//		}
		
//		// get selected country from available countries
//		var countryName = getCountryName(selectedCountry, availableCountries);
//        if(countryName === null) {
//            countryName = getCountryName(selectedCountry, defaultCountries);
//        }

//		// try to select (if fail, do nothing)
//		if(selectedCountry !== null) {
//        	// workaround to handle IE behaviour
//        	setTimeout(function () { 
//			    jqCountryControl.val(selectedCountry);
//        	}, 100);
//			capture.setCountryId(selectedCountry);
//			capture.setCountryName(countryName);
//		}
//	};
//	var bindCountryControlToCookie = function (countryControl, isControlSpecific) {
//		// changes to control will change the cookie (based control specific or not)
//		var context = {
//			"isControlSpecific" : isControlSpecific
//		};
//		$(countryControl).bind('change', context, function (e) {
//			var selectedCountry = $(this).val();
//			var cookieId = e.data.isControlSpecific ? $(this).attr("id") : "";
//			setCountryInCookie(selectedCountry, cookieId);
//		});
//	};
//	/**
//	 * Changes to country control will also change capture object's country property.
//	 */
//	this.bindCountryControlToCaptureObject = function (countryControl) {
//		// context
//		var context = {
//			"capture" : capture
//		};
//		// changes to control selection will change the address capture object
//		$(countryControl).bind('change', context, function (e) {
//			var selectedCountry = $(this).val();
//			e.data.capture.setCountryId(selectedCountry);
			
//			var countryName = getCountryName(selectedCountry, capture.getAvailableCountries());
//	        if(countryName === null) {
//	            countryName = getCountryName(selectedCountry, qas.search.ALL_COUNTRIES);
//	        }			
//			e.data.capture.setCountryName(countryName);
//		});
//	};
//	/**
//	 * Populate control with available and default countries.
//	 * The first selected value is, by priority 1) cookie 2) default 3) first available 4) first default.
//	 * Changes to control will also change the cookie (cookie either general for all controls or specific to a control).
//	 */
//	this.populateCountryControl = function (countryControl, isControlSpecific, successCallback, errorCallback) {
//		isControlSpecific = (isControlSpecific === null) ? false : isControlSpecific;
//		var jqCountryControl = $(countryControl);
//		// hide the countrol before getting data from server
//		jqCountryControl.hide();
//		// create a context so the callbacks can reference to the parameters in this function
//		var context = {
//			"countryControl" : jqCountryControl,
//			"successCallback" : successCallback,
//			"errorCallback" : errorCallback,
//			"defaultCountries" : defaultCountries,
//			"isControlSpecific" : isControlSpecific,
//			"capture" : capture
//		};
//		// get available countries
//		var availableCountries = capture.getAvailableCountries();
//		// if null, get available countries from server
//		if(availableCountries === null) {
//			//set success callback
//			capture.setSuccessCallback($.proxy(function (result) {
//				// remove all callbacks
//				this.capture.clearCallbacks();
//				for(var i = 0; i < this.countryControl.length; i++) {
//					var control = this.countryControl[i];
//					// result is available countries. populate to control
//					populateCountryControlWithData(control, result, this.defaultCountries);
//					// autoselect the country using cookie
//					autoselectCountryControl(control, this.isControlSpecific, result, this.defaultCountries);
//					// bind change event to control
//					bindCountryControlToCookie(control, this.isControlSpecific);
//                    // show control
//                    $(control).show();
//				}
//				// invoke successor callback
//				if( typeof this.successCallback === "function") {
//					this.successCallback(result);
//				}
//			}, context));
//			// set fail callback. if fail to get data, populate will only default countries
//			capture.setErrorCallback($.proxy(function (json, text, msg) {
//				var result = null;
//				// remove all callbacks
//				this.capture.clearCallbacks();
//				for(var i = 0; i < this.countryControl.length; i++) {
//					var control = this.countryControl[i];
//					// result is available countries. populate to control
//					populateCountryControlWithData(control, result, this.defaultCountries);
//					// autoselect the country using cookie
//					autoselectCountryControl(control, this.isControlSpecific, null, this.defaultCountries);
//					// bind change event to control
//					bindCountryControlToCookie(control, this.isControlSpecific);
//                    // show control
//                    $(control).show();
//				}
//				// invoke error callback
//				if( typeof this.errorCallback === 'function') {
//					this.errorCallback(json, text, msg);
//				}
//			}, context));
//			// get available countries from server
//			capture.getAllDataset();
//		} else {
//			// else if there's dataset, populate immediately using data
//			// result is available countries
//			for(var i = 0; i < jqCountryControl.length; i++) {
//				var control = jqCountryControl[i];
//				populateCountryControlWithData(jqCountryControl, availableCountries, defaultCountries);
//				// autoselect the country using cookie
//				autoselectCountryControl(control, isControlSpecific, availableCountries, defaultCountries);
//				// bind change event to control
//				bindCountryControlToCookie(jqCountryControl, isControlSpecific);
//                // show control
//                $(control).show();
//				// invoke successor callback
//				if( typeof successCallback === 'function') {
//					successCallback(availableCountries);
//				}
//			}
//		}
//	};
//};

qas.search.QASPass = function () {

    this.qasfinish = function() {
        if (window.qaspagename == "b2c") {
            var $this = $('.mp-ckt-qas');
            $this.addClass('mp-ckt-ajax').trigger('change');
        } else if (window.qaspagename == "b2b") {
            $("#err_msg_panel4").hide();
            $("body").prepend("<div class=\"overlay\"></div>");
            $(".overlay").css("opacity", 0.8).appendTo('body').delay(300).fadeIn();
            $("div#divLoading").center();
            $("div#divLoading").addClass('show');
            $("#payform").submit();
        } else if (window.qaspagename == "account") {
            $("#qas-addaddress-modal").hide();
            $("#qas-addaddress").show();
            $("#addaddress").hide();
            $("#skipqas").val("yes");
            $("#addressform").submit();
        }
    };

    this.qasNone = function() {
        if (window.qaspagename == "b2c") {
            $("#shipUndeliverable").val("true");
            $("#qasresult").hide();
            $("#skip_qas").val("yes");
            $('#qasresult').hide();
            $("#resultContainer").html("");
            $("#is_user_overridden").val(true);
            var $this = $('.mp-ckt-qas');
            $this.addClass('mp-ckt-ajax').trigger('change');
        } else if (window.qaspagename == "b2b") {
            $("body").prepend("<div class=\"overlay\"></div>");
            $(".overlay").css("opacity", 0.8).appendTo('body').delay(300).fadeIn();
            $("div#divLoading").center();
            $("div#divLoading").addClass('show');
            $("#skipqas").val("yes");
            $("#shipUndeliverable").val("true");
            $('#qasresult').hide();
            $("#resultContainer").html("");
            $("#is_user_overridden").val(true);
            $("#payform").submit();
        } else if (window.qaspagename == "account") {
            $("#is_user_overridden").val(true);
            $("#qas-addaddress-modal").hide();
            $("#qas-addaddress").show();
            $("#addaddress").hide();
            $("#skipqas").val("yes");
            $("#addressform").submit();
        }
    };
};

/**
 * @class Class for address searching.
 */
qas.search.QASCapture = function () {
	// local reference of this object
	var self = this;
	/**
	 * Ajax success callback function.
	 * @type function
	 * @default jQuery.noop()
	 */
	var ajaxSuccessCallback = function () {
	};
	/**
	 * Ajax error callback function.
	 * @type function
	 * @default jQuery.noop()
	 */
	var ajaxErrorCallback = function () {
	};
	/**
	 * Ajax setting to change URL of controller. Example is "Controller.aspx" for ASP.NET.
	 * @type string
	 * @default qas.search.DEFAULT_AJAX_URL
	 */
	var ajaxUrl = qas.search.DEFAULT_AJAX_URL;
	/**
	 * Ajax setting of invoking asynchronously / synchronously.
	 *
	 * @public
	 * @type boolean
	 * @default qas.config.Ajax.ajaxIsAsync;
	 */
	var ajaxIsAsync = qas.search.DEFAULT_AJAX_IS_ASYNC;
	/**
	 * Ajax setting of return data type.
	 *
	 * @public
	 * @type string
	 * @default qas.config.Ajax.ajaxDataType;
	 */
	var ajaxDataType = qas.search.DEFAULT_AJAX_DATA_TYPE;
	/**
	 * Ajax setting of invocation timeout.
	 *
	 * @public
	 * @type int
	 * @default qas.config.Ajax.ajaxTimeout;
	 */
	var ajaxTimeout = qas.search.DEFAULT_AJAX_TIMEOUT;
	/**
	 * Search setting to select country or datamap. (defaults automatically loaded
	 * from qas.config.Search object)
	 *
	 * @public
	 * @type string
	 * @default qas.config.Search.countryId
	 */
	var countryId = qas.search.DEFAULT_COUNTRY_ID;
    /**
     * Country name. Default is null.
     *
     * @public
     * @type string
     * @default qas.config.Search.countryId
     */
	var countryName = null;
	/**
	 * Search setting to select flatten mode. (defaults automatically loaded from
	 * qas.config.Search object)
	 *
	 * @public
	 * @type boolean
	 * @default qas.config.Search.isFlatten
	 */
	var flatten = qas.search.DEFAULT_IS_FLATTEN;
	/**
	 * Search setting to change intensity. (defaults automatically loaded from
	 * qas.config.Search object)
	 *
	 * @public
	 * @type qas.SearchIntensity
	 * @default qas.config.Search.intensity
	 */
	var intensity = qas.search.DEFAULT_INTENSITY;
	/**
	 * Search setting to change promptset. (defaults automatically loaded from
	 * qas.config.Search object)
	 *
	 * @public
	 * @type qas.SearchPromptSet
	 * @default qas.config.Search.promptset
	 */
	var promptset = qas.search.DEFAULT_PROMPTSET_TYPE;
	/**
	 * Search setting to change threshold. (defaults automatically loaded from
	 * qas.config.Search object)
	 *
	 * @public
	 * @type int
	 * @default qas.config.Search.threshold.
	 */
	var threshold = qas.search.DEFAULT_THRESHOLD;
	/**
	 * Search setting to change timeout during "Refine". (defaults automatically
	 * loaded from qas. object)
	 *
	 * @public
	 * @type int
	 * @default qas.config.Search.timeout.
	 */
	var timeout = qas.search.DEFAULT_TIMEOUT;
	/**
	 * Search setting to change engine type. (defaults automatically loaded from
	 * qas.config.Search object)
	 *
	 * @public
	 * @type qas.SearchEngineType
	 * @default qas.config.Search.engineType.
	 */
	var engineType = qas.search.DEFAULT_ENGINE;
	/**
	 * Search setting to change layout.
	 *
	 * @public
	 * @type string
	 * @default qas.config.Search.layout
	 */
	var layout = qas.search.DEFAULT_LAYOUT;
	/**
	 * Search setting to change localisation. Currently not implemented in
	 * server-side. (defaults automatically loaded from qas.config.Search object)
	 *
	 * @public
	 * @type string
	 * @default qas.config.Search.localisation
	 */
	var localisation = qas.search.DEFAULT_LOCALISATION;
	/**
	 * qas.config.Search object)
	 *
	 * @public
	 * @type string
	 * @default qas.config.Search.requestTag
	 */
	var requestTag = qas.search.DEFAULT_REQUEST_TAG;

	var formattedAddressInPickList = qas.search.DEFAULT_IS_FORMATTED_ADDRESS_IN_PICKLIST;

	var restMethods = {
		Search : "Search",
		CanSearch : "CanSearch",
		Refine : "Refine",
		GetAddress : "GetAddress",
		GetData : "GetData",
		GetLicenseInfo : "GetLicenseInfo",
		GetSystemInfo : "GetSystemInfo",
		GetDataMapDetail : "GetDataMapDetail",
		GetExampleAddresses : "GetExampleAddresses",
		GetLayouts : "GetLayouts",
		GetPromptset : "GetPromptSet"
	};

	// required and non-nullable params
	var restParamsNonNullable = [];
	restParamsNonNullable[restMethods.Search] = [];
	restParamsNonNullable[restMethods.CanSearch] = [];
	restParamsNonNullable[restMethods.Refine] = [];
	restParamsNonNullable[restMethods.GetAddress] = [];
	restParamsNonNullable[restMethods.GetData] = [];
	restParamsNonNullable[restMethods.GetLicenseInfo] = [];
	restParamsNonNullable[restMethods.GetSystemInfo] = [];
	restParamsNonNullable[restMethods.GetDataMapDetail] = [];
	restParamsNonNullable[restMethods.GetExampleAddresses] = [];
	restParamsNonNullable[restMethods.GetLayouts] = [];
	restParamsNonNullable[restMethods.GetPromptset] = [];

	/**
	 * Check for non nullable params, and if not valid param, return array of invalid params.
	 */
	var getNonNullableParams = function (restParamArr, nullableParamArr) {
		var i = 0;
		var iLen = nullableParamArr.length;
		var isInArray = false;
		var paramName = '';
		var invalidParams = [];

		for(; i < iLen; i++) {
			paramName = nullableParamArr[i];
			isInArray = qas.util.checkIsInArray(restParamArr, paramName);
			if(!isInArray) {
				invalidParams.push(paramName);
			}
		}
		return invalidParams;
	};
	var validateParams = function (currRestMethod, ajaxParams) {
		var invalidParams = getNonNullableParams(ajaxParams, restParamsNonNullable[currRestMethod]);
		if(invalidParams.length > 0) {
			ajaxErrorCallback();
		}
	};
	/**
	 * Invoke AJAX API based on the settings configured in the class.
	 * @param {object}
	 *          ajaxParams Required. Dictionary object. Contains all parameters
	 *          for AJAX invocation.
	 * @type void
	 */
	var invokeAjax = function (ajaxParams, internalSuccessCallback, internalErrorCallback) {
		// validate parameters
		validateParams(ajaxParams.method, ajaxParams);
		// context of success / error callback
		var context = {
			"ajaxSuccessCallback" : ajaxSuccessCallback,
			"ajaxErrorCallback" : ajaxErrorCallback,
			"internalSuccessCallback" : internalSuccessCallback,
			"internalErrorCallback" : internalErrorCallback
		};
		if (ajaxParams.search != null && ajaxParams.search.indexOf("|") >= 0) {
		    ajaxParams.search = ajaxParams.search.split("|").join("^");
		}
	    // invoke ajax method
	    // ajaxDataType
		$.ajax({
			type : "POST",
			cache : false,
			url : ajaxUrl,
			async : ajaxIsAsync,
			dataType: "html",
			timeout : ajaxTimeout,
			data : ajaxParams,
			success: $.proxy(function(data) {
			    var json = [];
			    try {
			        json = $.parseJSON(data.slice(0, -2));

			        // if return json does not have error, invoke success callback
			        if (json.error) {

			            if (typeof this.internalErrorCallback === 'function') {
			                this.internalErrorCallback(json.error, json.error.message, null);
			            }
			            if (typeof this.ajaxErrorCallback === 'function') {
			                this.ajaxErrorCallback(json.error, json.error.message, null);
			            }
			        } else if (!(json.result)) {

			            // else if no error and no result
			            if (typeof this.internalErrorCallback === 'function') {
			                this.internalErrorCallback(json.error, json.error.message, null);
			            }
			            if (typeof this.ajaxErrorCallback === 'function') {
			                this.ajaxErrorCallback(json.error, "JSON response missing result key.", null);
			            }
			        } else {
			            // else, no error, invoke success callback
			            if (typeof this.internalSuccessCallback === 'function') {
			                this.internalSuccessCallback(json.result);
			            }

			            if (typeof this.ajaxSuccessCallback === 'function') {
			                this.ajaxSuccessCallback(json.result);
			            }
			        }
			    } catch (e) {
			        //    $("#qastext").text("Output is not valid JSON: " + data);
			        sendErrorLog("QAS-SOAP-json-error", e.message + " | Json-response: " + data);
			        var qaspass = new qas.search.QASPass();
			        qaspass.qasNone();
			    }
			},context),
			error: function (jqXHR, textStatus, errorThrown) {
			    var searchAddress = "; Search Address: " + ajaxParams.search.split("|").join(";");
			    sendErrorLog("QAS-SOAP-ajax-error", textStatus + "; errorThrown: " + errorThrown + searchAddress);
				if( typeof this.internalErrorCallback === 'function') {
				    this.internalErrorCallback({}, textStatus, errorThrown);
				}

				if( typeof this.ajaxErrorCallback === 'function') {
				    this.ajaxErrorCallback({}, textStatus, errorThrown);
				}
			}
		});
	};
	/**
	 * Update the layout based on country ID.
	 */
	var updateLayout = function () {
		if( typeof qas.search.DEFAULT_COUNTRY_LAYOUT_MAP[countryId] !== "undefined") {
			layout = qas.search.DEFAULT_COUNTRY_LAYOUT_MAP[countryId];
		} else {
			layout = qas.search.DEFAULT_LAYOUT;
		}
	};
	this.checkIsAvailableCountry = function (countryId) {
		var isAvailableCountry = true;

		if(qas.search.AvailableCountries !== null) {
			var i = 0, iLen = qas.search.AvailableCountries.length;
			for(; i < iLen; i++) {
				if(qas.search.AvailableCountries[i].ID === countryId) {
					isAvailableCountry = true;
				}
			}
		}

		return isAvailableCountry;
	};
	this.getAvailableCountries = function () {
		return qas.search.AvailableCountries;
	};
	this.clearCallbacks = function () {
		ajaxSuccessCallback = $.noop;
		ajaxErrorCallback = $.noop;
	};
	this.getLayout = function () {
		return layout;
	};
	this.getRequestTag = function () {
		return requestTag;
	};
	this.getCountryId = function () {
		return countryId;
	};
	this.getCountryName = function () {
	    return countryName;
	};
	this.getPromptsetType = function () {
		return promptset;
	};
	this.getLocalisation = function () {
		return localisation;
	};
	this.getTimeout = function () {
		return timeout;
	};
	this.getThreshold = function () {
		return threshold;
	};
	this.getIntensity = function () {
		return intensity;
	};
	this.getIsFlatten = function () {
		return flatten;
	};
	this.getEngine = function () {
		return engineType;
	};
	this.getIsFormattedAddressInPickList = function () {
		return formattedAddressInPickList;
	};
	/**
	 * Set request tag, used in tagging search performed and saved in On Demand server.
	 * @type string
	 */
	this.setRequestTag = function (paramRequestTag) {
		requestTag = paramRequestTag;
	};
	/**
	 * Set country id to be used in subsequent searches.
	 * @type string
	 */
	this.setCountryId = function (paramCountryId) {
		countryId = paramCountryId;
		// update the layout after changes on country ID.
		updateLayout();
	};
	
    this.setCountryName = function (paramCountryName) {
        countryName = paramCountryName;
    };
	/**
	 * Set promptset to be used in subsequent searches.
	 * @type qas.const.PROMPTSET_TYPE
	 */
	this.setPromptsetType = function (paramPromptsetType) {
		promptset = paramPromptsetType;
	};
	/**
	 * Set localisation, used in subsequent searches.
	 * @type string
	 */
	this.setLocalisation = function (paramLocalisation) {
		localisation = paramLocalisation;
	};
	/**
	 * Set timeout to be used when refining search.
	 * @type number
	 */
	this.setTimeout = function (paramTimeout) {
		timeout = paramTimeout;
	};
	/**
	 * Set threshold to be used when refining search.
	 * @type number
	 */
	this.setThreshold = function (paramThreshold) {
		threshold = paramThreshold;
	};
	/**
	 * Set intensity to be used in subsequent searches.
	 * @type qas.const.INTENSITY
	 */
	this.setIntensity = function (paramIntensity) {
		intensity = paramIntensity;
	};
	/**
	 * Set flag to indicate intensity to be used in subsequent searches.
	 * @type boolean
	 */
	this.setIsFlatten = function (paramIsFlatten) {
		flatten = paramIsFlatten;
	};
	/**
	 * Set engine type to be used in subsequent searches.
	 * @type qas.const.ENGINE
	 */
	this.setEngine = function (paramEngine) {
		engineType = paramEngine;
	};
	/**
	 * Set flag to indicate is formatted address in picklist
	 * @type boolean
	 */
	this.setIsFormattedAddressInPickList = function (paramIsFormattedAddressInPicklist) {
		formattedAddressInPickList = paramIsFormattedAddressInPicklist;
	};
	/**
	 * Set function to be invoked when success.
	 * @type boolean
	 */
	this.setSuccessCallback = function (callbackFunction) {
		ajaxSuccessCallback = callbackFunction;
	};
	/**
	 * Set function to be invoked when error.
	 * @type boolean
	 */
	this.setErrorCallback = function (callbackFunction) {
		ajaxErrorCallback = callbackFunction;
	};
	/**
	 * Perform a search.
	 *
	 * @param {string}
	 *          countryId Country ID to use.
	 * @param {string[]}
	 *          searchStrArr Search string array. When only one line needed, a
	 *          single element array should be passed as parameter.
	 * @param {string}
	 *          promptset Promptset name to use. Configured in OnDemand server.
	 * @param {string}
	 *          layout Layout name to use. Configured in OnDemand server.
	 * @param {string}
	 *          requestTag Request Tag. Used to text to tag a search for improving
	 *          search history management.
	 * @type void
	 */
	this.search = function (searchText) {
		var ajaxParams = {
			"method" : restMethods.Search,
			"search" : searchText,
			"countryId" : self.getCountryId(),
			"engine" : self.getEngine(),
			"flatten" : self.getIsFlatten(),
			"intensity" : self.getIntensity(),
			"promptset" : self.getPromptsetType(),
			"threshold" : self.getThreshold(),
			"timeout" : self.getTimeout(),
			"layout" : self.getLayout(),
			"formattedAddressInPicklist" : self.getIsFormattedAddressInPickList(),
			"requestTag" : self.getRequestTag(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	/**
	 * Refine a search.
	 *
	 * @param {string}
	 *          moniker Required. Country ID to use.
	 * @param {string}
	 *          refinementText Optional. Text used for refinement. If step-in,
	 *          refinement text is not needed.
	 * @type void
	 */
	this.refine = function (moniker, refinementText) {
		var ajaxParams = {
			"method" : restMethods.Refine,
			"moniker" : moniker,
			"refinement" : refinementText,
			"layout" : self.getLayout(),
			"formattedAddressInPicklist" : self.getIsFormattedAddressInPickList(),
			"threshold" : self.getThreshold(),
			"timeout" : self.getTimeout(),
			"requestTag" : self.getRequestTag(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	/**
	 * Get formatted address.
	 *
	 * @param {string}
	 *          moniker Required.
	 * @param {string}
	 *          layout Required.
	 * @type void
	 */
	this.getFormattedAddress = function (moniker) {
		var ajaxParams = {
			"method" : restMethods.GetAddress,
			"moniker" : moniker,
			"layout" : self.getLayout(),
			"requestTag" : self.getRequestTag(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	/**
	 * Checks whether a country ID and layout name can be used in combination for
	 * a search.
	 *
	 * @param {string}
	 *          countryId Country ID. Configured in OnDemand server.
	 * @param {string}
	 *          layout Layout name. Configured in OnDemand server.
	 * @type void
	 */
	this.canSearch = function () {
		var ajaxParams = {
			"method" : restMethods.CanSearch,
			"countryId" : self.getCountryId(),
			"engine" : self.getEngine(),
			"flatten" : self.getIsFlatten(),
			"intensity" : self.getIntensity(),
			"promptset" : self.getPromptsetType(),
			"threshold" : self.getThreshold(),
			"timeout" : self.getTimeout(),
			"layout" : self.getLayout(),
			"localisation" : self.getLocalisation()
		};
		return invokeAjax(ajaxParams);
	};
	/**
	 * Get all available countries and ids related to these countries.
	 *
	 * @param {string}
	 *          moniker Required.
	 * @param {string}
	 *          layout Required.
	 * @type void
	 */
	this.getAllDataset = function () {
		var ajaxParams = {
			"method" : restMethods.GetData,
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams, function (result) {
			qas.search.AvailableCountries = result;
		});
	};
	/**
	 * Get specific details of a specific data.
	 *
	 * @param {string}
	 *          countryId Required.
	 * @type void
	 */
	this.getDataMapDetail = function (countryId) {
		var ajaxParams = {
			"method" : restMethods.GetDataMapDetail,
			"countryId" : self.getCountryId(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	/**
	 * Get all layouts available for a specific dataset.
	 *
	 * @param {string}
	 *          countryId Required.
	 * @type void
	 */
	this.getAllLayout = function () {
		var ajaxParams = {
			"method" : restMethods.GetLayouts,
			"countryId" : self.getCountryId(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	/**
	 * Get all example addresses for a specific combination of dataset and layout.
	 *
	 * @param {string}
	 *          countryId Required.
	 * @param {string}
	 *          layout Required.
	 * @type void
	 */
	this.getExampleAddresses = function () {
		var ajaxParams = {
			"method" : restMethods.GetExampleAddresses,
			"countryId" : self.getCountryId(),
			"layout" : self.getLayout(),
			"requestTag" : self.getRequestTag(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	this.getLicenseInfo = function () {
		var ajaxParams = {
			"method" : restMethods.GetLicenseInfo,
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	this.getPromptSet = function () {
		var ajaxParams = {
			"method" : restMethods.GetPromptset,
			"countryId" : self.getCountryId(),
			"engine" : self.getEngine(),
			"flatten" : self.getIsFlatten(),
			"intensity" : self.getIntensity(),
			"promptset" : self.getPromptsetType(),
			"threshold" : self.getThreshold(),
			"timeout" : self.getTimeout(),
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};
	this.getSystemInfo = function () {
		var ajaxParams = {
			"method" : restMethods.GetSystemInfo,
			"localisation" : self.getLocalisation()
		};
		invokeAjax(ajaxParams);
	};

    var sendErrorLog = function(source, message) {
        var href = '/checkout/apierrormessage';

        $.ajax(href, {
            type: 'POST',
            data: {
                'apitype': source,
                'errmessage': message
            },
            dataType: 'text',
            success: function() {
                
            },
            error: function() {
            }
        });
    };

	// CONSTRUCTOR LOGIC
	updateLayout();
};
