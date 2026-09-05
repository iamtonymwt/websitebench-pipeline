/*********************************************************************************************************************************************************************
 **********************************************************************************************************************************************************************
 *
 *QAS Best Practices AJAX Sample Code
 *Release v5.1
 *Date: 2/7/2011
 *
 **********************************************************************************************************************************************************************
 *
 *Tested with:
 *	Proweb:
 *		v6.45
 *	Browsers:
 *		Firefox v3.6
 *		Chrome v6.0
 *		Safari v4.0
 *		Opera v10.62
 *		IE v6, v7, v8
 *
 **********************************************************************************************************************************************************************
 *
 *This code is written to be used in conjunction with QAS Pro Web and the provided Common Classes along with a language specific qas_proxy file. It is dependent
 *on both jQuery and jQueryUI.
 *
 *This code processes all addresses on a web page through the proweb engine and requests interaction from an end-user when appropriate. All cleansed
 *addresses are then returned to the proper form. All unique addresses will be processed exactly once, if there are two addresses with the same input ignoring case
 *and after extraneous spaces have been stripped they will be considered the same and processed only once. If any user interaction is needed, it will be requested
 *only once and used for both addresses.
 *
 *
 *All settings are created at the top of the code and can be changed to properly integrate into a website. QAS_Verify() is the function that should be called by
 *a website in order to initiate address verificaton. The Classes are as follows:
 *
 *Main
 *	Instantiates all objects
 *	Loops through addresses
 *	Calls function to return all results
 *	Calls pre and post validation functions
 *
 *Address
 *	Retrieves and stores addresses
 *	Determines unique addresses
 *	Builds search strings
 *	Stores cleaned addresses
 *	Returns addresses to web page
 *
 *Clean
 *	Used to clean a single address by making an AJAX call to qas_proxy
 *	Cleans/Refines/Formats addresses
 *	Stores verifylevel/cleansed result/picklist
 *
 *Business
 *	All business logic is handled here
 *	Controls interaction
 *
 *Interface
 *	creates div tags
 *	populates tags with appropriate messages
 *	displays pop up
 *	accepts user interaction
 *
 **********************************************************************************************************************************************************************
 *
 *Programmer: Jonathan Reimels
 *Date: 10/5/2010
 *
 **********************************************************************************************************************************************************************
 *Please log any internal changes to the code here with the following format(Programmer, Date, Reason for change, Change made)
 *
 *UPDATES:
 *
 *Programmer:  Zulfiqar Ahmad
 *Date: 12/15/10
 *Reason: Renaming/Reorganization for clarity and consistency with prior versions of BP
 *Change: Alphabetized countries in stripPostCode switch statement.   JS updated to match proxy name changes: dpv->dpvstatus; matchtype->verifylevel; isfull->fulladdress
 *
 *Programmer:  Jonathan Reimels
 *Date: 12/15/10
 *Reason: Messaging added for when secondary info inputed on prompt is out of range, as per older versions of BP
 *Change:  Additions to lines 156, 164, 979-986, 994-1001
 *
 *Programmer: Ng Kah Ching
 *Date 8/2/11
 *Reason: Update prior version of BP to use Implementation Code framework
 *Change: Using JSON instead of xml, datamap will be get from OnDemand ws, update logic to handle search result
 **********************************************************************************************************************************************************************
 *********************************************************************************************************************************************************************/

/*********************************************************************************************************************************************************************
 *
 *Settings
 *
 *Set all variables here to properly integrate into website
 *
 *********************************************************************************************************************************************************************/

/*global $*/
/**
 * @namespace Namespace to provide qas feature
 */
var qas = qas || {};

/**
 * @namespace Namespace to provide verification feature
 */
qas.verification = qas.verification || {};

/**
 * This is an array of string arrays, the id's for each set of address fields (excluding country fields) should be listed
 * in an individual string array. These should be listed to match with the proweb config.
 * For each cleaned result, the first item (ie Address Line 1) in the config will go into the first field in the string array
 * @type (array)
 */
qas.verification.address_field_ids = [["x_ship_to_address", "x_ship_to_address2", "x_ship_to_address3", "x_ship_to_city", "UsStates", "CanadaStates", "Zipcode"], ["x_address", "x_address2", "x_address3", "x_city", "UsStates", "CanadaStates", "x_zip"], ["selected_address", "selected_address2", "selected_address3", "selected_city", "selected_UsStates", "selected_CanadaStates", "selected_zip"]];

qas.verification.edit_address_ids = ["editadd1", "editadd2", "editadd3", "editcity", "editstate", "editzip"];

qas.verification.use_array_position_id = "use_array_position";

/**
 * Country field id's, these should be listed in the same order as the string arrays in qas.verification.address_field_ids.
 * If a layout doesn't have a country field, then enter false in for the appropriate address within the string.
 * @type (array)
 */
qas.verification.country_fields_ids = ["Country", "x_country", "selected_country"];

/**
 * This is only for Canadian addresses.
 * The proweb configuration should be setup to include LVR and Building name as one of the last lines in order to properly handle CAN apartments.
 * This variable should be set to the line number within the config that contains these fields.
 * @type (int)
 */
qas.verification.lvr = 7;

/**
 *	Regular Expression to check for LVR  
 */
qas.verification.lvr_regular_expression = /\|?\d+[A-Za-z]*\s*-\s*\d+/;

/**
 * prompt user for information to correct address when needed
 * @type (boolean)
 */
qas.verification.interaction_required = true;

//number of lines to display to user in an interaction required address, this will prevent, additional data, such as dpv indicator, or lat/long from being displayed to user
/**
 * number of lines to display to user in an interaction required address,
 * to prevent additional data to be displayed to user.
 * @type (int)
 */
qas.verification.display_lines = 6;

//Instantiate global instance for QASCapture
var capture = new qas.search.QASCapture();
capture.setEngine(qas.search.EngineType.VERIFICATION);
capture.setIsFlatten(true);

var qaspass = new qas.search.QASPass();
var currentUSStatesId = "UsStates";
var currentCanadaStatesId = "CanadaStates";

//Instantiate global instance of LanguageController
//var languageController = new qas.lang.LanguageController();
/**
 *
 * @class Verification Init
 */
qas.verification.Init = function () {	
	var error = null;
	
};
/**
 * to clear Verification form fields value
 * @class QAS ClearForm 
 */
qas.verification.QAS_ClearForm = function () {
	$(".verifyFields").val("");
}
/**
 * the initial function to call from the webpage in order to initiate address verification, set onclick events inside this function
 * @class QAS Verify
 */
qas.verification.QAS_Verify = function (pre = null, pos = null) {
	//set any onclick events and submit buttons to use pre and post validation
	var preOnclick = pre;
	var postOnclick = pos;
	var buttonID = "";
	var isValid = false;
	var i;
	var m = null;

    //check if the country is selected
	var v_use_array_position_id = parseInt($("#" + qas.verification.use_array_position_id).val());
	if ($.isNumeric(v_use_array_position_id) && v_use_array_position_id <= qas.verification.address_field_ids.length) {
	    qas.verification.address_field_ids = new Array(qas.verification.address_field_ids[v_use_array_position_id - 1]);
	    qas.verification.country_fields_ids = new Array(qas.verification.country_fields_ids[v_use_array_position_id - 1]);
	    currentUSStatesId = "selected_" + currentUSStatesId;
	    currentCanadaStatesId = "selected_" + currentCanadaStatesId;
	}
	for (i = 0; i < qas.verification.country_fields_ids.length; i++) {
		var dropDownValue = $('#' + qas.verification.country_fields_ids[i]).val();

		if ((dropDownValue)) {
			isValid = true;
			break;
		}
	}

	//if country not selected, alert
	if (!isValid) {
		alert("Please select the country code");
		return false;
	}

	if (preOnclick === null) {
		m = new qas.verification.Main(postOnclick, buttonID);
		m.process();
	} else if (preOnclick()) {
		m = new qas.verification.Main(postOnclick, buttonID);
		m.process();
	}

	return false;
};
/*********************************************************************************************************************************************************************
 *
 *Main Class
 *
 *Public Methods
 *	process		- instantiate Interface and Clean, perform clean and sent result to Business
 *	next		- store cleaned address, move on to next address
 *	finish		- put cleaned addresses in form, submit form
 *	ajaxError	- handle any errors during the ajax call to proweb
 *
 *********************************************************************************************************************************************************************/

qas.verification.Main = function (clickEvent, buttonID) {

	//Private Variables
	var me = this;

	var m_click = clickEvent;
	var m_button = buttonID;

    //instantiate Address, and build the search string
	var add = new qas.verification.Address(qas.verification.address_field_ids, qas.verification.country_fields_ids);
	var strings = add.getSearchStrings();
	var countries = add.getSearchCountries();
	var orig = add.getOriginalAddresses();

	var inter;

	var clean;

	//keep track of address to be processed (the 'next' method controls this)
	var procIndex = 0;

	/**
	 * process an address - part 1, search the address
	 * @type void
	 */
	this.process = function () {
		//hide select boxes to handle bug with ie6, where select boxes show through the pop-up window
		//$('select').css('visibility', 'hidden');
	    
		//instantiate Interface to handle all user interaction
		inter = new qas.verification.Interface(me.returnEarly);

		//instantiate Clean, to process address
		clean = new qas.verification.Clean(strings[procIndex], countries[procIndex], me.ajaxError);

		//if string isn't false process it (false string means it is either an empty address or the country isn't in Avaliable DATA_SETS)
		if (strings[procIndex]) {
			//open the waiting widget, clean address, close waiting widget
			clean.search(me.process2);
		} else {
			//if string is false use original address
			clean.result = orig[procIndex];
			me.next();
		}
	};
	/**
	 * process an address - part 2, process the result after callback from ajax call
	 * @type void
	 */
	this.process2 = function () {

		//instantiate a new Business object and process the cleaned result
		var business = new qas.verification.Business(me.next, clean, orig[procIndex], inter);

		//call appropriate business function to process address depending on whether end-user interaction is allowed
		if (qas.verification.interaction_required) {
			business.processResult();
		} else {
			business.noInteraction();
		}
	};
	/**
	 * this is called in order to store an address and increment procIndex so that if another address exists it will be cleaned
	 * @type void
	 */
	this.next = function () {
		//add verify level to result, commented out so DPVDefault layout can display result correctly
		//clean.result.push(clean.verifylevel);

		//store cleaned address
		add.storeCleanedAddress(clean.result);

		//increase procIndex to point to the next address
		procIndex++;

		//if another address exists, process it, otherwise move to end
		if (procIndex < strings.length) {
			me.process();
		} else {
			me.finish();
		}
	};
	/**
	 * returns cleaned addresses to webpage, calls submit functions if any exist
	 * @type void
	 */
	this.finish = function () {
		//unhide select boxes to handle bug with ie6, where select boxes show through the pop-up window
		//$('select').css('visibility', '');

		//return cleaned addresses
		add.returnCleanAddresses();

		//if an onclick event exists, call it
		if (m_click !== null) {
			m_click();
		}

	    qaspass.qasfinish();

	    //if (window.qaspagename == "b2b") {
	    //    $("#err_msg_panel4").hide();
	    //    $("body").prepend("<div class=\"overlay\"></div>");
	    //    $(".overlay").css("opacity", 0.8).appendTo('body').delay(300).fadeIn();
	    //    $("div#divLoading").center();
	    //    $("div#divLoading").addClass('show');
	    //    $("#payform").submit();
	    //} else if (window.qaspagename == "b2c") {
	    //    var $this = $('.mp-ckt-qas');
	    //    $this.addClass('mp-ckt-ajax').trigger('change');
	    //}

	    //if a submit button exists, click it
	    //if (m_button !== "") {
	    //	$('#' + m_button).attr('onclick', '');
	    //	$('#' + m_button).parent('form').attr('onsubmit', '');
	    //	$('#' + m_button).click();
	    //}
	};
	/**
	 * used for clicks on the edit button to return any addresses already cleaned
	 * @type void
	 */
	this.returnEarly = function () {
		//unhide select boxes to handle bug with ie6, where select boxes show through the pop-up window
		//$('select').css('visibility', '');

		//return cleaned addresses
		add.returnCleanAddresses();
	};
	/**
	 * handle ajax errors
	 * @param json
	 * @param text
	 * @param msg
	 */
	this.ajaxError = function (json, text, msg) {

		if (text === "timeout") {
			//set match type to timeout
			clean.verifylevel = "Timeout";
		} else {
			//set match type to error
			clean.verifylevel = "Error";
		}

		//if display errors is set, then display the error
		if (qas.search.DISPLAY_ERROR) {
		    alert("The On Demand server is not available\n" + text);
		}

		//set restult to the original address entered
		clean.result = orig[procIndex];

		//move onto next record
		me.next();
	};
};
//End Main Class

/*********************************************************************************************************************************************************************
 *
 *Address Class
 *
 *Public Methods
 *	getSearchStrings		- returns an array of strings ready to be sent to qas, a value of false means the address should not be processed
 *	getSearchCountries		- returns an array of countries corresponding to the search strings
 *	getOriginalAddresses	- returns an array of original addresses corresponding to the search strings
 *	storeCleanedAddress		- stores a cleaned address
 *	returnCleanAddresses	- returns cleaned addresses to the webpage
 *
 *********************************************************************************************************************************************************************/

qas.verification.Address = function (addressIds, countryIds) {
	
	/**************************PRIVATE**************************/
	var ids = addressIds;
	var cIds = countryIds;
	var addresses = [];
	var uniqueAddresses = [];
	var uniqueTracker = [];
	var searchStrings = [];
	var searchCountries = [];
	var cleanedAddresses = [];
	var i;
	var j;

	//retrieve address values from forms and return array
	var getAddresses = function () {
		//loop through forms
		for (i = 0; i < ids.length; i++) {
			//a variable to temporarily store an address form
			var tempAddress = [];

		    //get the country from the form
			var c3 = $('#' + cIds[i]).val();
			if (c3 == "US") c3 = "USA";
			if (c3 == "CA") c3 = "CAN";

			//loop through fields in form
			for (j = 0; j < ids[i].length; j++) {
				//get data in address field
				var fieldValue = $('#' + ids[i][j]).val();

				//if this field is undefined and display errors is on, display an error, otherwise this will be handled later
				if (fieldValue === undefined) {
					if (qas.search.DISPLAY_ERROR) {
						alert("ID '" + ids[i][j] + "' is undefined");
					}
				} else {
				    //trim whitespace
				    //'"[]<>(){}|&#\/;

				    fieldValue = fieldValue.replace(/^\s+|\s+$/g, "");
				    fieldValue = fieldValue.split("'").join("");
				    fieldValue = fieldValue.split("\"").join("");
				    fieldValue = fieldValue.split("[").join("");
				    fieldValue = fieldValue.split("]").join("");
				    fieldValue = fieldValue.split("<").join("");
				    fieldValue = fieldValue.split(">").join("");
				    fieldValue = fieldValue.split("(").join("");
				    fieldValue = fieldValue.split(")").join("");
				    fieldValue = fieldValue.split("{").join("");
				    fieldValue = fieldValue.split("}").join("");
				    fieldValue = fieldValue.split("|").join("");
				    fieldValue = fieldValue.split("&").join("");
				    fieldValue = fieldValue.split("#").join("");
				    fieldValue = fieldValue.split("\\").join("");
				   // fieldValue = fieldValue.split("/").join("");
				    fieldValue = fieldValue.split(";").join("");
				    fieldValue = fieldValue.split("^").join("");
				}

			    //push the value into the temporary variable
				
				if (ids[i][j] == currentUSStatesId || ids[i][j] == currentCanadaStatesId) {
				    if (c3 == "USA" && ids[i][j] == currentUSStatesId) {
				        tempAddress.push(fieldValue);
				    } else if (c3 == "CAN" && ids[i][j] == currentCanadaStatesId) {
				        tempAddress.push(fieldValue);
				    }
				} else {
				    tempAddress.push(fieldValue);
				}
			}

			//push country into the temporary variable
			tempAddress.push(c3);

			//push temporary address into array of addresses
			addresses.push(tempAddress);
		}
	};
	

	

	//determine which forms contain unique addresses
	var getUnique = function () {

	    uniqueTracker = new Array(addresses.length);

		var isUnique = true;
		var j = 0;

		//loop through addresses
		for (i = 0; i < addresses.length; i++) {
			//assume address is unique, point uniqueTracker to where address will be added in uniqueAddresses, and set isUnique to true
			uniqueTracker[i] = uniqueAddresses.length;
			isUnique = true;
			j = 0;

			//loop through unique addresses until the current address either matches a unique
			//address or no more unique addresses are left, in which case the address is unique
			//and is added to the unique address list - if this is the first address it will
			//be unique by default
			while (isUnique && (j < uniqueAddresses.length)) {
				if (addresses[i].toString().toLowerCase() === uniqueAddresses[j].toString().toLowerCase()) {
					isUnique = false;
					uniqueTracker[i] = j;
				}
				j++;
			}

			if (isUnique) {
				uniqueAddresses.push(addresses[i]);
			}
		}
	};
	
	//check if an address should be cleaned
	var cleanCheck = function (address, country) {
		var addNotEmpty = false;
		var j = 0;

		//if an address is empty or has an undefined field, then false will be returned
		while (j < address.length) {
			if (address[j] !== "") {
				addNotEmpty = true;
			}

			if (address[j] === undefined) {
				return false;
			}
			j++;
		}

		//if the country is not in the list, return false
		if (addNotEmpty) {
			addNotEmpty = capture.checkIsAvailableCountry(country);

			if (!addNotEmpty) {
				if (window.console) {
					console.log("The country is not in available datamap, by default accept them");
				}
			}
		}
		return addNotEmpty;
	};
	
	//build the SearchString array from the unique addresses
	var buildSearchStrings = function () {
		for (i = 0; i < uniqueAddresses.length; i++) {
			searchCountries.push(uniqueAddresses[i].pop());

			if (cleanCheck(uniqueAddresses[i], searchCountries[i])) {
				searchStrings.push(uniqueAddresses[i].join("|"));
			} else {
				searchStrings.push(false);
			}
		}
	};
	
	//return cleansed address
	var returnAddresses = function () {
	    var isUSCountry = false
		for (i = 0; i < ids.length; i++) {
			//if edit is clicked, not all addresses will have been validated, only update validated addresses in this case
			if (cleanedAddresses[uniqueTracker[i]] !== undefined) {
			    for (j = 0; j < ids[i].length; j++) {
			        var c3 = $('#' + cIds[i]).val();
			        var currentAddressValue = cleanedAddresses[uniqueTracker[i]][j];

			        if (j >= 4) {
			            if (c3 == "US" && j == 4) {
							$('#' + currentUSStatesId).val(currentAddressValue);
			            } else if (c3 == "CA" && j == 4) {
			                $('#' + currentCanadaStatesId).val(currentAddressValue);
			            } else if (j == 5 && i == 0) {
			                $('#Zipcode').val(currentAddressValue);
							$('#selected_zip').val(currentAddressValue);
			            } else if (j == 5 && i == 1) {
			                $('#x_zip').val(currentAddressValue);
			            } else if (j == 6) {
			                var residential = "3";
			                if (currentAddressValue == "N") residential = "0";
			                else if (currentAddressValue == "Y") residential = "1";
			                if (i == 0) {
			                    $('#residential').val(residential);
			                    $('#selected_residential').val(residential);
			                } else {
			                    $('#b_residential').val(residential);
			                }
			            }
			        } else {
						$('#' + ids[i][j]).val(currentAddressValue);
			        }
				}
			}
		}
	};

	/**************************END OF PRIVATE**************************/
	
	/**************************PUBLIC**************************/
	this.getSearchStrings = function () {
		return searchStrings;
	};
	this.getSearchCountries = function () {
		return searchCountries;
	};
	this.getOriginalAddresses = function () {
		return uniqueAddresses;
	};
	this.storeCleanedAddress = function (cleanAddress) {
		cleanedAddresses.push(cleanAddress);
	};
	this.returnCleanAddresses = function () {
		returnAddresses();
	};
	/**************************END OF PUBLIC**************************/
	//constructor
	getAddresses();
	getUnique();
	buildSearchStrings();

};
//end Address Class

/*********************************************************************************************************************************************************************
 *
 *Clean Class
 *
 *Public Properties
 *	result		- cleaned result from proweb, either a picklist, or a cleaned address
 *	verifylevel	- match type from the cleaning process
 *	dpv			- dpv information
 *	country		- country of cleaned address
 *
 *Public Methods
 *	search					- main search, to be used to process an address
 *	searchPremisesPartial	- reprocesses a premises partial address
 *	searchStreetPartial		- reprocesses a street partial address
 *	searchDPVPartial		- reprocesses an address that failed dpv
 *	formatAddress			- get a formatted address
 *	refineAddress			- refine on a picklist
 *
 *********************************************************************************************************************************************************************/

qas.verification.Clean = function (searchString, country_3, ajaxErr) {

	var me = this;
	var m_ajaxErr = ajaxErr;
	var premClean = false;
	var strClean = false;
	var partialAddress = "";
	var m_callback;

	/**************************PRIVATE**************************/

	var origSearchString = searchString;
	var i;

	//append each line from the returned xml to result
	var saveAddress = function (line) {
		me.result.push(line);
	};
	
	//build array of picklist items from the returned xml
	var savePickList = function (items) {
		////try-catch here

		var partialText = items.PartialAddress;
		var addressText = items.Text;
		var postCode = items.Postcode;
		var moniker = items.Moniker;
		var fulladdress = items.IsFullAddress;

		me.result.push({
			"partialText" : partialText,
			"addressText" : addressText,
			"postCode" : postCode,
			"moniker" : moniker,
			"fulladdress" : fulladdress
		});
	};
	
	//get a partial address within a picklist that is not a full address
	//this is used to append building or apt info, and research on the resulting address
	var getPartialAddress = function () {
		for (i = 0; i < me.result.length; i++) {
			if (me.result[i].fulladdress.toString().toLowerCase() === "false") {
				return me.result[i].partialText;
			}
		}
		return null;
	};
	
	//strip postcodes from strings based on country
	//used to strip the postcode out of premises and street
	//partial addresses prior to address being re-submitted
	var stripPostCode = function (str) {
	    if (me.country == "USA") {
	        str = str.replace(/-\d{4}$/, "");
	    }

		return str;
	};
	
	//process result from ajax call
	var saveResult = function (json) {

		me.verifylevel = json.VerifyLevel;
		me.dpv = "";
		var i;

		if (json.Address) {
			me.dpv = json.Address.DPVStatus;
		} else {
			me.dpv = json.DPVStatus;
		}

		//if a premisesPartial is searched on and a premisesPartial is returned,
		//keep old result, so as not to retain the incorectly entered premise info
		if (premClean && (me.verifylevel === "PremisesPartial")) {
			premClean = false;
		} else if (strClean && (me.verifylevel === "StreetPartial")) {
			strClean = false;
		} else {
			//re-initialize this.result
			me.result = [];
			premClean = false;
			strClean = false;

			//save each line of the address if result is 'Verified' or 'InteractionRequired' || (me.dpv == 0)
			if ((me.verifylevel === "Verified") || (me.verifylevel === "InteractionRequired") || (me.verifylevel === "VerifiedStreet") || (me.verifylevel === "VerifiedPlace") || (me.dpv)) {

				var addressLine = [];
				
				if (json.Address) {
					addressLine = json.Address.AddressLines;
				} else if (json.AddressLines) {
					addressLine = json.AddressLines;
				} else if (json.Picklist.Items) {
					if (json.Picklist.Items.length > 1) {
						me.verifylevel = "PremisesPartial";
						for (i = 0; i < json.Picklist.Items.length; i++) {
							savePickList(json.Picklist.Items[i]);
						}
						partialAddress = getPartialAddress();
						if (partialAddress === null) {
							me.verifylevel = "Multiple";
						}
					} else {
						me.result.push(json.Picklist.Items[0].Text);
					}
				}
				for (i = 0; i < addressLine.length; i++) {
				    var addresslines = addressLine[i].Line;
				    if (i == 5 && me.country == "CAN") {
				        addresslines = addresslines.replace(' ','');
				    }
				    saveAddress(addresslines);
				}
			} else { //otherwise save each picklist item

				if (typeof json.Picklist === 'undefined') {
					for (i = 0; i < json.Items.length; i++) {
						savePickList(json.Items[i]);
					}
					me.verifylevel = "PremisesPartial";
				} else if (typeof json.Picklist.Items !== 'undefined' && json.Picklist.Items !== null) {
					for (i = 0; i < json.Picklist.Items.length; i++) {
						savePickList(json.Picklist.Items[i]);
					}
				}

				if ((me.verifylevel === "PremisesPartial") || (me.verifylevel === "StreetPartial")) {
					partialAddress = getPartialAddress();
					if (partialAddress === null) {
						me.verifylevel = "Multiple";
					}
				}
			}
		}
		m_callback();
	};
	
	//build up ajax parameters for verification search, and call ajax search
	var doSearch = function (address, c3, ajaxError) {

		capture.setSuccessCallback(function (json) {
			saveResult(json);
		});
		capture.setErrorCallback(function (json, text, msg) {
			ajaxError(json, text, msg);
		});
		capture.setCountryId(c3);

		capture.search(address);
	};
	//build up ajax parameters for format, and call ajax
	var doFormat = function (moniker, ajaxError) {

		capture.setSuccessCallback(function (json) {
			saveResult(json);
		});
		capture.setErrorCallback(function (json, text, msg) {
			ajaxError(json, text, msg);
		});
		capture.getFormattedAddress(moniker);
	};
	//build up ajax parameters for refine, and call ajax
	var doRefine = function (moniker, ajaxError) {

		capture.setSuccessCallback(function (json) {
			saveResult(json);
		});
		capture.setErrorCallback(function (json, text, msg) {
			ajaxError(json, text, msg);
		});
		capture.refine(moniker, "");
	};
	
	/**************************END OF PRIVATE**************************/
	
	/**************************PUBLIC**************************/

	this.result = [];
	this.verifylevel = "";
	this.dpv = "";

	this.country = country_3;

	this.search = function (callback) {
		m_callback = callback;
		doSearch(origSearchString, me.country, m_ajaxErr);
	};
	this.searchPremisesPartial = function (aptNo, callback) {

	    var partAddress = "";
	    var splitString = origSearchString.split("|");
	    for (i = 0; i < splitString.length; i++) {
	        if (i == 3) {
	            partAddress += ", ";
	        } else if (splitString[i] != "") {
	            partAddress += " ";
	        }
	        partAddress += splitString[i];
	        
	    }

	    m_callback = callback;
		premClean = true;
		//strip the +4 from a partial address and append the apt to the end of the first line
		var noPost = stripPostCode(partAddress);
		var aptAddress = noPost.replace(/,/, " # " + aptNo + ",");

		//process address
		doSearch(aptAddress, me.country, m_ajaxErr);
	};
	this.searchStreetPartial = function (buildingNo, callback) {
		m_callback = callback;
		strClean = true;
		//strip the +4 from a partial address and append the building number to the start of the first line
		var noPost = stripPostCode(partialAddress);
		var buildAddress = buildingNo + " " + noPost;

		//process address
		doSearch(buildAddress, me.country, m_ajaxErr);
	};
	this.searchDPVPartial = function (buildingNo, callback) {
		m_callback = callback;

		//replace old building number with new building number to original address
		var wholeAddress = me.result.join("|");
		wholeAddress = wholeAddress.replace(/\|?\d+\w*\s/, "|" + buildingNo + " ");

		//process address
		doSearch(wholeAddress, me.country, m_ajaxErr);
	};
	this.formatAddress = function (moniker, callback) {
		m_callback = callback;

		//format on the moniker
		doFormat(moniker, m_ajaxErr);
	};
	this.refineAddress = function (moniker, callback) {
		m_callback = callback;
		//refine on the moniker
		doRefine(moniker, m_ajaxErr);
	};
	this.editSearch = function (editAdd, callback) {
		m_callback = callback;
		doSearch(editAdd, me.country, m_ajaxErr);
	};
	/**************************END OF PUBLIC**************************/
};
//end Clean Class

/*********************************************************************************************************************************************************************
 *
 *Business Class
 *
 *The public methods of this class are used to process a cleansed address, prompt for interaction if necessary, handle interaction, pass address back to main
 *
 *********************************************************************************************************************************************************************/

qas.verification.Business = function (callback, clean, orig, inter) {
	var me = this;

	var m_callback = callback;
	var m_clean = clean;
	var m_orig = orig;
	var m_inter = inter;

	//used for double street partials and double premise partials
	var previousMatch = "";
	var count = 0;

	//handle addresses with no end-user interaction
	this.noInteraction = function () {
		if ((m_clean.verifylevel === "Verified") || (m_clean.verifylevel === "InteractionRequired")) {
			m_callback();
		} else {
			me.useOriginal();
		}
	};
	
	this.acceptInter = function () {
		//accept interaction address
		m_callback();
	};
	this.acceptMoniker = function (moniker) {
		//get formatted address associated with moniker and accept it
		m_clean.formatAddress(moniker, m_callback);
	};
	this.refineApt = function () {
		//clean a premisespartial address and process it
		var aptNo = $('#QAS_RefineText').val();
		m_clean.searchPremisesPartial(aptNo, me.processResult);
	};
	this.refineBuild = function () {
		//clean a streetpartial address and process it
		var buildNo = $('#QAS_RefineText').val();
		m_clean.searchStreetPartial(buildNo, me.processResult);
	};
	this.refineDPV = function () {
		//clean an address that failed dpv and process it
		var buildNo = $('#QAS_RefineText').val();
		m_clean.searchDPVPartial(buildNo, me.processResult);
	};
	this.appendApt = function () {
		//append apt to address and accept it
		var aptNo = $('#QAS_RefineText').val();

		var aptIndex = 0;
		var aptLine = false;

		//find address line one and add apt to it
		while ((!aptLine) && (aptIndex < m_clean.result.length)) {
			if (m_clean.result[aptIndex].search(/^\d+\s/) !== -1) {
				aptLine = true;
				m_clean.result[aptIndex] = aptNo + "-" + m_clean.result[aptIndex];
			}
			aptIndex++;
		}
		m_callback();
	};
	this.refineMult = function (moniker) {
		//refine on multiple address and process the result
		m_clean.refineAddress(moniker, me.processResult);
	};
	this.useOriginal = function () {
		//accept orignally entered address
		m_clean.result = m_orig;
		m_callback();
	};
	var aptCheck = function (lvrLine) {
		var isApt = "";

		//check if address should have apt
		isApt = m_clean.result[lvrLine];

		//if address should have apt, check if it already does have an apt
		if (isApt) {
			//search on wholeaddress as address line 1 is unknown
			var wholeAddress = m_clean.result.join("|");
			if (wholeAddress.search(qas.verification.lvr_regular_expression) !== -1) {
				return true;
			} else {
				return false;
			}
		} else {
			return true;
		}
	};
	this.editSearch = function (editAdd) {
		//search the editted address
		previousMatch = "";
		count = 0;
		m_clean.editSearch(editAdd, me.processResult);
	};

	this.compareSearch = function(oriAddress, verifiedAddress, myCountry) {
	    if (oriAddress.length >= 6 && verifiedAddress.length >= 6) {
	        for (var i = 0; i < oriAddress.length; i++) {
	            var oAddr = oriAddress[i];
	            var nAddr = verifiedAddress[i];
	            if (oAddr != undefined) {
	                oAddr = oAddr.toLowerCase().replace(".", "");
	                if (i == 5 && myCountry == "USA" && /^\d{5}(?:-?([a-zA-Z0-9]{4}))?$/.test(oAddr) && oAddr.length >= 9) { // Ignore +4 Zip Code for US when comparing
	                    oAddr = oAddr.substring(0, 5);
	                }
	            }
	            if (nAddr != undefined) {
	                nAddr = nAddr.toLowerCase().replace(".", "");
	                if (i == 5 && myCountry == "USA" && /^\d{5}(?:-?([a-zA-Z0-9]{4}))?$/.test(nAddr) && nAddr.length >= 9) {
	                    nAddr = nAddr.substring(0, 5);
	                }
	            }

	            if (oAddr != nAddr) {
	                return false;
	            }
	        }
	    }
	    return true;
	};
	
	this.processResult = function () {
		count++;

		//handle address based on verifylevel
		switch (m_clean.verifylevel) {
		case "Verified":
			//if address is USE, then check DPV status
			if (m_clean.country === "USA") {
				//if dpv is not confirmed or dpv seed hit, prompt for Building Number
				if (((clean.dpv === "DPVNotConfirmed") || (clean.dpv === "DPVSeedHit")) && count <= 1) {
					m_inter.setDPVPartial(m_orig, me.refineDPV, me.useOriginal, me.editSearch);
					m_inter.display();
				} else if (clean.dpv === "DPVConfirmedMissingSec") {
					//if dpv is missing secondary, treat address as an Interactino Required
					m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
					m_inter.display();
				} else { //otherwise, dpv was passed or not set. Accept the address
				    if (me.compareSearch(m_orig, m_clean.result, m_clean.country)) {
				        m_callback();
				    } else {
				        m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
				        m_inter.display();
				    }
				}
			} else if (m_clean.country === "CAN") { //if address is Canadian, check to see if there should be an apartment
				//if there should be an apt and the address currently doesn't have one, prompt for an apt
				if (!aptCheck(qas.verification.lvr - 1)) {
					m_inter.setAptAppend(m_orig, me.appendApt, m_callback, me.useOriginal, me.editSearch);
					m_inter.display();
				} else { //otherwise, apartment was already entered, or address doesn't need an apt
				    if (me.compareSearch(m_orig, m_clean.result, m_clean.country)) {
				        m_callback();
				    } else {
				        m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
				        m_inter.display();
				    }
				}
			} else { //all other countries, accept verified address
			    if (me.compareSearch(m_orig, m_clean.result, m_clean.country)) {
			        m_callback();
			    } else {
			        m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
			        m_inter.display();
			    }
				
			}
			break;

		case "InteractionRequired":

			//if there should be an apt and the address currently doesn't have one, prompt for an apt
			if ((m_clean.country === "CAN") && (!aptCheck(qas.verification.lvr - 1))) {
				m_inter.setAptAppend(m_orig, me.appendApt, m_callback, me.useOriginal, me.editSearch);
				m_inter.display();
			} else if (count > 1) { //if interaction has already happened and resulting address is an interaction required, accept the address without further interaction
				m_callback();
			} else { //otherwise display interaction required dialog
				m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
				m_inter.display();
			}
			break;

		case "VerifiedPlace":
			//if there should be an apt and the address currently doesn't have one, prompt for an apt
			if ((m_clean.country === "CAN") && (!aptCheck(qas.verification.lvr - 1))) {
				m_inter.setAptAppend(m_orig, me.appendApt, m_callback, me.useOriginal, me.editSearch);
				m_inter.display();
			} else if (count > 1) { //if interaction has already happened and resulting address is an interaction required, accept the address without further interaction
				m_callback();
			} else { //otherwise display interaction required dialog
				m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
				m_inter.display();
			}
			break;

		case "VerifiedStreet":
			//if there should be an apt and the address currently doesn't have one, prompt for an apt
			if ((m_clean.country === "CAN") && (!aptCheck(qas.verification.lvr - 1))) {
				m_inter.setAptAppend(m_orig, me.appendApt, m_callback, me.useOriginal, me.editSearch);
				m_inter.display();
			} else if (count > 1) { //if interaction has already happened and resulting address is an interaction required, accept the address without further interaction
				m_callback();
			} else { //otherwise display interaction required dialog
				m_inter.setInterReq(m_clean.result, m_orig, me.acceptInter, me.useOriginal, me.editSearch);
				m_inter.display();
			}
			break;

		case "PremisesPartial":

			//display premises partial dialog
			m_inter.setPremisesPartial(m_clean.result, m_orig, me.refineApt, me.acceptMoniker, me.useOriginal, me.editSearch);
			m_inter.display();

			//if previous address was a PremisesPartial, inform user that invalid range was entered
			if (previousMatch === "PremisesPartial") {
			    //alert("The On Demand server is not available");
			}

			//set previous match type
			previousMatch = "PremisesPartial";
			break;

		case "StreetPartial":

			//display street partial dialog
			m_inter.setStreetPartial(m_clean.result, m_orig, me.refineBuild, me.acceptMoniker, me.useOriginal, me.editSearch);
			m_inter.display();

			//if previous address was a StreetPartial, inform user that invalid range was entered
			if (previousMatch === "StreetPartial") {
			    alert("Building number is not within the valid range of addresses");
			}

			//set previous match type
			previousMatch = "StreetPartial";
			break;

		case "Multiple":
			//display multiple dialog
			m_inter.setMultiple(m_clean.result, m_orig, me.acceptMoniker, me.refineMult, me.useOriginal, me.editSearch);
			m_inter.display();
			break;

		case "None":
			//display none dialog
			m_inter.setNone(m_orig, me.useOriginal, me.editSearch);
			//m_inter.display();
			break;
		}
	};
};
//end Business Class

/*********************************************************************************************************************************************************************
 *
 *Interface Class
 *
 *	Display dialog to user
 *
 *********************************************************************************************************************************************************************/

qas.verification.Interface = function (editCall) {
	
	/**************************PRIVATE**************************/
	var me = this;
	var m_editCall = editCall;
	var m_pickList;
	var m_orig;
	var m_pickHtml = "";
	var m_buttonpickHtml = "";
	var origAddressHtml = "";
	var i = 0;		
	//create a picklist
	var buildPick = function () {
		//reinitialize
		m_pickHtml = "";
		
		for (i = 0; i < m_pickList.length; i++) {
		    if (m_pickList[i].fulladdress.toString().toLowerCase() === "true") {
		        var chkbutton = "";
		        if (i == 0) {
		            chkbutton = "checked";
		        }
                
			    m_pickHtml += "<li class='picklistItem' onclick=\"$('.verifyAddressButton').css('display', 'none'); $('#picklistItem_" + i + "').css('display', 'block');\">";
			    m_pickHtml += "    <label class='radio-inline'>";
			    m_pickHtml += "	       <input name='radioAvsGroup' id='radio_picklistItem_" + i + "' class='picklistItemText vPicklistItemText' title='" + m_pickList[i].addressText + " " + m_pickList[i].postCode + "' value='picklistItem_" + i + "' " + chkbutton + " type='radio'>" + m_pickList[i].addressText + " " + m_pickList[i].postCode;
			    m_pickHtml += "	   </label>";
			    m_pickHtml += "</li>";
			    var dpbutton = "none";
			    if (i == 0) {
			        dpbutton = "block";
			    }			
			    m_buttonpickHtml += "<input type='button' class='verifyAddressButton' id='picklistItem_" + i + "' style='display:" + dpbutton + "' moniker='" + m_pickList[i].moniker + "' tabindex='0' value='Use Suggested Address'></input>";
		        //m_pickHtml += "<tr><td NOWRAP><a href='#' class='QAS_StepIn' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].addressText + "</a></td><td NOWRAP><a href='#' class='QAS_StepIn' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].postCode + "</a></td></tr>";
			}
			//else {
				//m_pickHtml += "<tr><td NOWRAP>" + m_pickList[i].addressText + "</td><td NOWRAP>" + m_pickList[i].postCode + "</td></tr>";
			//}
		}
	};
	//create a picklist for multiple address, all items must be clickable
	var buildMultPick = function () {
		//reinitialize		
		m_pickHtml = "";		
		if (m_pickList != undefined) {
		    for (i = 0; i < m_pickList.length; i++) {
		        var chkbutton = "";
		        if (i == 0) {
		            chkbutton = "checked";
		        }

		        var dpbutton = "none";
		        if (i == 0) {
		            dpbutton = "block";
		        }
				
		        if (m_pickList[i].fulladdress.toString().toLowerCase() === "true") {
		            m_pickHtml += "<li class='picklistItem' onclick=\"$('.verifyAddressButton').css('display', 'none'); $('#picklistStepItem_" + i + "').css('display', 'block');\">";
		            m_pickHtml += "    <label class='radio-inline'>";
		            m_pickHtml += "	       <input name='radioAvsGroup' id='radio_picklistStepItem_" + i + "' class='picklistItemText vPicklistItemText' title='" + m_pickList[i].addressText + " " + m_pickList[i].postCode + "' value='picklistItem_" + i + "' " + chkbutton + " type='radio'>" + m_pickList[i].addressText + " " + m_pickList[i].postCode;
		            m_pickHtml += "	   </label>";
		            m_pickHtml += "</li>";

		            m_buttonpickHtml += "<input type='button' class='verifyAddressButton' id='picklistStepItem_" + i + "' style='display:" + dpbutton + "' moniker='" + m_pickList[i].moniker + "' tabindex='0' value='Use Suggested Address'></input>";
		        } else {
		            m_pickHtml += "<li class='picklistItem' onclick=\"$('.verifyAddressButton').css('display', 'none'); $('#picklistRefineItem_" + i + "').css('display', 'block');\">";
		            m_pickHtml += "    <label class='radio-inline'>";
		            m_pickHtml += "	       <input name='radioAvsGroup' id='radio_picklistRefineItem_" + i + "' class='picklistItemText vPicklistItemText' title='" + m_pickList[i].addressText + " " + m_pickList[i].postCode + "' value='picklistItem_" + i + "' " + chkbutton + " type='radio'>" + m_pickList[i].addressText + " " + m_pickList[i].postCode;
		            m_pickHtml += "	   </label>";
		            m_pickHtml += "</li>";

		            m_buttonpickHtml += "<input type='button' class='verifyAddressButton' id='picklistRefineItem_" + i + "' style='display:" + dpbutton + "' moniker='" + m_pickList[i].moniker + "' tabindex='0' value='Use Suggested Address'>Use Suggested Address</input>";
				}
		        //if (m_pickList[i].fulladdress.toString().toLowerCase() === "true") {
		        //	m_pickHtml += "<tr><td NOWRAP><a href='#' class='QAS_StepIn' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].addressText + "</a></td><td NOWRAP><a href='#' class='QAS_StepIn' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].postCode + "</a></td></tr>";
		        //} else {
		        //	m_pickHtml += "<tr><td NOWRAP><a href='#' class='QAS_Refine' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].addressText + "</a></td><td NOWRAP><a href='#' class='QAS_Refine' moniker='" + m_pickList[i].moniker + "'>" + m_pickList[i].postCode + "</a></td></tr>";
		        //}
		    }
		}
		
	};
	//build display of original address and button to click
	var buildRightSide = function (origCallback, editCallback) {
		var origHtml = "";
		var editHtml = "";
        
		for (i = 0; i < m_orig.length; i++) {
		    if (i == 3) {
		        origHtml += ", ";
		    } else if (m_orig[i] != "") {
		        origHtml += " ";
		    }
		    origHtml += m_orig[i];
		}

	    origAddressHtml = origHtml;

	};
	//load div tags to page and set modal dialogs
	var load = function () {	
		//remove the dialog if it already exists
	    $("#resultContainer").remove();
		
		var qasDialog = "<div id='resultContainer' class='resultContainer'></div>";

	    //add div tag to page
		$("#displaycontainer").append(qasDialog);
		
	};
	/**************************END OF PRIVATE**************************/
	
	/**************************PUBLIC**************************/
	//display interaction dialog
	this.display = function () {
		//window.scroll(0, 0);

	    $("#qasresult").show();	
		$('#QAS_RefineText').focus();
		$('.verifyAddressButton').focus();		
	    if ($("#qas-addaddress").length) {
	        $("#qas-addaddress").hide();
	        $("#qas-addaddress-modal").show();			
	    }
	    

		//remove close button from top right of dialog
		//$('.ui-dialog-titlebar-close').css('display', 'none');

		//remove the default focus from interaction required button(so that it is not highlighted as if mouse is hovering on it)
		//$('#QAS_RefineBtn').blur();
		//$('.QAS_Header').focus();
	};
	//set dialog to handle interaction required address
	this.setInterReq = function (cleaned, orig, acceptCallback, origCallback, editCallback) {
		m_orig = orig;

		setShowWindow("InterReq", "", cleaned, orig, origCallback, editCallback);

		$('#refineButton').click(function () {
		    acceptCallback();
		    $('#qasresult').hide();
		    $("#resultContainer").html("");
		});
	};
	//set dialog to handle premises partial addresses
	this.setPremisesPartial = function (pickList, orig, refineCallback, monikerCallback, origCallback, editCallback) {
		m_pickList = pickList;
		m_orig = orig;

		setShowWindow("PremisesPartial", pickList, "", orig, origCallback, editCallback);

    //add onclick event to the button
	        $('#refineButton').click(function() {
	            if($('#QAS_RefineText').val() === "") { //if no value was entered in field, display error message
	                alert("No value entered");
	        } else {
	                refineCallback();
	                $('#qasresult').hide();
	                $("#resultContainer").html("");
	        }
	        });
	        
	        for(var index = 0; index < m_pickList.length; index++) {
	            var $picklistItem = $("#picklistItem_" +index);
                $("#radio_picklistItem_0").click();
	            // Bind click event.
	            $picklistItem.click(function() {
	                var mon = $(this).attr('moniker');
	                monikerCallback(mon);
	                $('#qasresult').hide();
	                $("#resultContainer").html("");
	                });
	        }
	};
	//set dialog to handle street partial addresses
	this.setStreetPartial = function (pickList, orig, refineCallback, monikerCallback, origCallback, editCallback) {
	    m_pickList = pickList;
	    m_orig = orig;

	    //build picklist to display and right side of dialog

	    setShowWindow("StreetPartial", pickList, "", orig, origCallback, editCallback);

	    //add onclick event to the button
	    $('#refineButton').click(function () {
	        if ($('#QAS_RefineText').val() === "") { //if no value was entered in field, display error message
	            alert("No value entered");
	        } else {
	            refineCallback();
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        }
	    });
	    
	    for (var index = 0; index < m_pickList.length; index++) {
	        var $picklistItem = $("#picklistItem_" + index);

	        // Bind click event.
	        $picklistItem.click(function () {
	            var mon = $(this).attr('moniker');
	            monikerCallback(mon);
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        });
	    }
	};
	//set dialog to handle addresses that fail dpv
	this.setDPVPartial = function (orig, refineCallback, origCallback, editCallback) {
	    m_orig = orig;

	    setShowWindow("DPVPartial", "", "", orig, origCallback, editCallback);

	    //add onclick event to the button
	    $('#refineButton').click(function () {
	        if ($('#QAS_RefineText').val() === "") { //if no value was entered in field, display error message
	            alert("No value entered");
	        } else {
	            refineCallback();
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        }
	    });
	    
	};
	//set dialog to handle addresses missing apt info
	this.setAptAppend = function (orig, refineCallback, noAptCallback, origCallback, editCallback) {
	    m_orig = orig;

	    setShowWindow("AptAppend", "", "", orig, origCallback, editCallback);

	    $('#refineButton').click(function () {
	        if ($('#QAS_RefineText').val() === "") { //if no value was entered in field, display error message
	            alert("No value entered");
	        } else {
	            noAptCallback();
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        }
	    });
	};
	//set dialog to handle multiple addresses
	this.setMultiple = function (pickList, orig, formatCallback, refineCallback, origCallback, editCallback) {
	    m_pickList = pickList;
	    m_orig = orig;

	    setShowWindow("Multiple", "", "", orig, origCallback, editCallback);
	    
	    for (var j = 0; j < m_pickList.length; j++) {
	        var $picklistStepItem = $("#picklistStepItem_" + j);
	        var $picklistRefineItem = $("#picklistRefineItem_" + j);

	        // Bind click event.
	        $picklistStepItem.click(function () {
	            var mon = $(this).attr('moniker');
	            formatCallback(mon);
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        });

	        $picklistRefineItem.click(function () {
	            var mon = $(this).attr('moniker');
	            refineCallback(mon);
	            $('#qasresult').hide();
	            $("#resultContainer").html("");
	        });
	    }
	};
	//set display for none verifylevel
	this.setNone = function (orig, origCallback, editCallback) {
	    m_orig = orig;
	    
	    //setShowWindow("None", "", "", orig, origCallback, editCallback);

	    //$('#refineButton').click(function () {
	    //    origCallback();
	    //    $('#qasresult').hide();
	    //    $("#resultContainer").html("");
	    //});
	    //if (window.qaspagename == "b2c") {
	    //    $("#shipUndeliverable").val("true");
	    //    $("#qasresult").hide();
	    //    $("#skip_qas").val("yes");
	    //    $('#qasresult').hide();
	    //    $("#resultContainer").html("");
	    //    var $this = $('.mp-ckt-qas');
	    //    $this.addClass('mp-ckt-ajax').trigger('change');
	    //} else {
	    //    $("body").prepend("<div class=\"overlay\"></div>");
	    //    $(".overlay").css("opacity", 0.8).appendTo('body').delay(300).fadeIn();
	    //    $("div#divLoading").center();
	    //    $("div#divLoading").addClass('show');
	    //    $("#skipqas").val("yes");
	    //    $("#shipUndeliverable").val("true");
	    //    $('#qasresult').hide();
	    //    $("#resultContainer").html("");
	    //    $("#payform").submit();
	    //}
	    qaspass.qasNone();

	};

	var setShowWindow = function (type, pickList, cleaned, orig, origCallback, editCallback) {
	    var qastype = "";
	    var headerMessage = "";
	    var textMessage = "";
	    var buttonMessage = "";
	    var titleMessage = "";
	    var error = "";

	    switch(type) {
	        case "InterReq":
	            qastype = "IR";
	            headerMessage = "<b>We think that your address may be incorrect or incomplete.</b>";
	            textMessage = "";
	            titleMessage = "Recommended Address:";
	            buttonMessage = "Use suggested address";				
	            break;
	        case "PremisesPartial":
	            qastype = "PP";
	            headerMessage = "<b>Sorry, we think your apartment/suite/unit is missing or wrong.</b><br>";
	            textMessage = " <b>Confirm your Apartment/Suite/Unit number: </b>";
	            buttonMessage = "Confirm number";
	            titleMessage = "Recommended Address:";
	            error = "Secondary information not within valid range";
	            break;
	        case "StreetPartial":
	            qastype = "SP";
	            headerMessage = "<b>Sorry, we do not recognize your house or building number.</b><br>";
	            textMessage = " <b>Confirm your House/Building number: </b>";
	            buttonMessage = "Confirm number";
	            titleMessage = "Recommended Address:";
	            error = "Primary information not within valid range";
	            break;
	        case "DPVPartial":
	            qastype = "DP";
	            headerMessage = "<b>Sorry, we do not recognize your house or building number.</b><br>";
	            textMessage ="<b>Confirm your House/Building number: </b>";
	            buttonMessage = "Confirm number";
	            titleMessage = "Recommended Address:";
	            error = "Secondary information not within valid range";
	            break;
	        case "AptAppend":
	            qastype = "AA";
	            headerMessage = "<b>Sorry, we do not recognize your house or building number.</b><br>";
	            textMessage = "<b>Confirm your House/Building number: </b>";
	            buttonMessage = "Confirm number";
	            titleMessage = "Recommended Address:";
	            error = "Secondary information not within valid range";
	            break;
	        case "Multiple":
	            qastype = "MP";
	            headerMessage = "<b>We found more than one match for your address.</b><br>";
	            titleMessage = " <b>Our suggested matches: </b>";				
	            break;
	        case "None":
	            qastype = "NP";
	            headerMessage = "<b>*Your address may be undeliverable</b>";
	            titleMessage = "<b>Address could not be verified</b>";
	            buttonMessage = "Keep Address As Entered";
	            break;
	    }

	    var cleanedHtml = "";
	    if (qastype == "IR" && cleaned.length > 0) {
	        
	        for (i = 0; i < qas.verification.display_lines; i++) {
	            if (i == 3) {
	                cleanedHtml += ", ";
	            } else if (cleaned[i] != "") {
	                cleanedHtml += " ";
	            }
	            cleanedHtml += cleaned[i];
			}
	    } else if (qastype == "PP" || qastype == "SP") {
            buildPick();
        } else if (qastype == "MP") {			
            buildMultPick();
	    } else if (qastype == "NP") {
	        for (i = 0; i < orig.length; i++) {
	            if (i == 3) {
	                cleanedHtml += ", ";
	            } else if (orig[i] != "") {
	                cleanedHtml += " ";
	            }
	            cleanedHtml += orig[i];
	        }
	    }
        buildRightSide(origCallback, editCallback);

        var html = "<div id='refineContainer' class='refineContainer'>";
        html += "       <span id='refineHeader' class='refineHeader'>" + headerMessage + "</span>";
        if (qastype == "PP" || qastype == "SP" || qastype == "DP" || qastype == "AA") {
	        html += "	    <div class='confirm-apt col-md-12 span-12'>";
	        html += "		    <span id='refineText' class='refineText'>" + textMessage + "</span>";
	        html += "		    <input id='QAS_RefineText' class='refineBox' type='text'>";
            html += "		    <input id='refineButton' class='refineButton refineVerifyAddressButton' value='" + buttonMessage + "' type='button'><br>";
            html += "		    <span id='refineError' class='refineError'></span>";
	        html += "	    </div>";
	    }
	    html += "   </div>";
	    if (qastype == "PP" || qastype == "SP" || qastype == "DP" || qastype == "AA" || qastype == "MP") {
	        html += "   <div></div>";
	        html += "   <div class='lb-list-container col-md-6 span-6'>";
	        html += "	    <h3 class='lb-list-header'>" + titleMessage + "</h3>";
	        html += "	    <div class='divpicklist col-md-12 span-12'>";
	        if (qastype == "PP" || qastype == "SP" || qastype == "MP") {
	            html += "		    <ul id='picklist' class='picklist'>";
	            html += m_pickHtml;
	            html += "		    </ul>";
	        }
	        html += "	    </div>";
	        html += "	    <div class='cta_address col-md-12 span-12'>";
	        if (qastype == "PP" || qastype == "SP" || qastype == "MP") {
	            html += m_buttonpickHtml;
	        }
	        html += "           <a class=\"keepAddressButton\"  style='display:block' tabindex='0'>Address not listed?</a>";
	        html += "	    </div>";
	        html += "   </div>";
	        html += "   <div class='lb-list-container col-md-6 span-6'>";
	    } else if (qastype == "IR" || qastype == "NP") {
	        html += "   <div class='lb-list-container col-md-6 span-5-5'>";
	        html += "	    <h3 class='lb-list-header'>" + titleMessage + "</h3>";
	        html += "	    <div class='divpicklist col-md-12 span-12'><p class='address-entered' id='picklist'>" + cleanedHtml + "</p></div>";
	        html += "	    <div class='cta_address col-md-12 span-12'>";
	        if (qastype == "IR" || qastype == "NP") {
	            html += "		    <input id='refineButton' class='refineButton verifyAddressButton' value='" + buttonMessage + "' type='button'>";
	        } else {
	            html += "None";
	        }
	        html += "           <a class=\"keepAddressButton\" style='display:block' tabindex='0'>Address not listed?</a>";
	        html += "	    </div>";
	        html += "   </div>";
	        html += "   <div class='lb-list-container col-md-6 span-5-5'>";
	    }
	    html += "	    <h3 class='lb-list-header'>You Entered:</h3>";
        html += "	    <div class='divpicklist col-md-12 span-12'>";
        html += "		    <p class='address-entered' id='picklist'>" + origAddressHtml + "</p>";
        html += "	    </div>";
        html += "   </div>";

        $("#resultContainer").html(html);

        if (window.qaspagename == "b2c") {
            $.fn.center = function () {
                this.css("padding-top", ($(window).height() - this.height()) / 2 + $(window).scrollTop() + "px");
                return this;
            };
            $(".modal-modal").center();
        }
        $("#qasresult").show("fast", function () {
            $("html, body").animate({
                scrollTop: $(".modal-modal-content").offset().top
            }, 500);
        });
	};
	/**************************END OF PUBLIC**************************/
	
	//constructor
	load();

};	//end Interface Class