
$(document).ready(function () {
    $("#contactform").submit(function () {
        return checkform(this);
    });
    if ($("#chkInternational")[0].checked) {
        $("#country").show();
    } else {
        $("#country").hide();
    }
    $("input:radio[name=Tabs]").each(function() {
        if ($(this).is(':checked')) {
            var value = ($(this).data("name"));
            switch (value) {
                case "customer":
                    $("#ui-id-1").click();
                    break;
                case "tech":
                    $("#ui-id-2").click();
                    break;
                case "return":
                    $("#ui-id-3").click();
                    break;
                case "sales":
                    $("#ui-id-4").click();
                    break;
                case "corporate":
                    $("#ui-id-5").click();
                    break;
                default:
                    $("#ui-id-1").click();
                    break;
            }
        }
    });
    
});

function LoadState(value) {
    if (value) {
        $("#divState").show();
        if ($("#chkInternational")[0].checked) {
            $("#country").show();
        }
    } else {
        $("#divState").hide();
        $("#country").hide();
    }
}

function LoadCustomerID(value) {
    if (value) {
        $("#divCustomerID").show();
    } else {
        $("#divCustomerID").hide();
    }
}

/*function kbcheck(thisform) {
    for (var i = 0; i < thisform.search_opt.length; i++) {
        if (thisform.search_opt[i].checked) {
            var option = thisform.search_opt[i].value;
        }
    }

    if (thisform.kb_keyword.value == "") {
        alert('Enter a keyword to search articles or downloads.');
        thisform.kb_keyword.focus();
        return false;
    }
    else {
        thisform.action = "/home/driver_download.asp?s_keyword=" + thisform.kb_keyword.value;
    }
    return true;
}*/

function checkform(thisform) {
    $("#contactus").remove();
    if ($('#phone-num').val() === '') {
        $("#AreaCode").val('');
        $("#Exchange").val('');
        $("#Number").val('');
        $("#Extension").val('');
    }
    var message = false;
    if (thisform.Name.value == '' || thisform.Name.value.trim() == "") {
        $(thisform.Name).css("border", "1px solid red");
        $(thisform.Name).next().text('This field is required')
        $(thisform.Name).next().css("color", "red")
        message = true;
    }
    else {
        $(thisform.Name).css("border", "1px solid #ccc");
        $(thisform.Name).next().text('')
    }

    if (thisform.Email.value == '') {
        $(thisform.Email).css("border", "1px solid red");
        $(thisform.Email).next().text('This field is required');
        $(thisform.Email).next().css("color", "red");
        message = true;
    }
    else if (thisform.Email.value.indexOf('@') == -1) {
        $(thisform.Email).css("border", "1px solid red");
        $(thisform.Email).next().text('This is not a valid email address');
        $(thisform.Email).next().css("color", "red");
        message = true;
    }
    else {
        $(thisform.Email).css("border", "1px solid #ccc");
        $(thisform.Email).next().text('')
    }

    if (thisform.ConfirmEmail.value == '') {
        $(thisform.ConfirmEmail).css("border", "1px solid red");
        $(thisform.ConfirmEmail).next().text('This field is required')
        $(thisform.ConfirmEmail).next().css("color", "red")
        message = true;
    }
    else {
        $(thisform.ConfirmEmail).css("border", "1px solid #ccc");
        $(thisform.ConfirmEmail).next().text('')
    }

    if (thisform.Email.value != thisform.ConfirmEmail.value) {
        $(thisform.ConfirmEmail).css("border", "1px solid red");
        $(thisform.ConfirmEmail).next().text('The email addresses you entered does not seem to match. Please review your email addresses and ensure that these are matching.');
        $(thisform.ConfirmEmail).next().css("color", "red");
        message = true;
    }

    if (thisform.TellUs.value == '') {
        $(thisform.TellUs).css("border", "1px solid red");
        $(thisform.TellUs).next().text('This field is required')
        $(thisform.TellUs).next().css("color", "red")
        message = true;
    }
    else {
        $(thisform.TellUs).css("border", "1px solid #ccc");
        $(thisform.TellUs).next().text('')
    }

    if (message == true) {
        return false;
    }
    var value = "false";
    var category = "";
    $("input:radio[name=Tabs]").each(function () {
        if ($(this).is(':checked')) {
            value = "true";
            category = ($(this).data("name"));
        }
    });
    
    if (value == "false") {
        alert('Please select category question.');
        return false;
    }

    if (category == 'sales') {

        if (thisform.State.value == '' && !thisform.chkInternational.checked) {
            alert('Please enter state name.');
            return false;
        }

        if (thisform.chkInternational.checked && thisform.Country.value == '') {
            alert('Please enter country name.');
            return false;
        }

        var rexp = new RegExp("^[0-9]*$");
        if (!rexp.test(thisform.txtCustomerID.value)) {
            alert('Please enter a valid customer ID. Must be all numbers.');
            return false;
        }
    }

    var rexp = new RegExp("^[0-9]*$");
    if (thisform.AreaCode.value != '') {
        if (thisform.AreaCode.value.length != 3 || !rexp.test(thisform.AreaCode.value)) {
            alert('Please input valid phone number');
            thisform.AreaCode.focus();
            return false;
        }
    }
    if (thisform.Exchange.value != '') {
        if (thisform.Exchange.value.length != 3 || !rexp.test(thisform.Exchange.value)) {
            alert('Please input valid phone number');
            thisform.Exchange.focus();
            return false;
        }
    }
    if (thisform.Number.value != '') {
        if (thisform.Number.value.length != 4 || !rexp.test(thisform.Number.value)) {
            alert('Please input valid phone number');
            thisform.Number.focus();
            return false;
        }
    }
    if (thisform.Extension.value != '') {
        if (!rexp.test(thisform.Extension.value)) {
            alert('Please input valid phone number');
            thisform.Extension.focus();
            return false;
        }
    }

    if (thisform.OrderNumber.value != '') {
        if (!rexp.test(thisform.OrderNumber.value)) {
            alert('Please input valid order number');
            thisform.OrderNumber.focus();
            return false;
        }
    }

    if (typeof helpdeskQuery == 'function') {
        var helpdeskQuery1Value = "";
        $("input:radio[name=Tabs]").each(function () {
            if ($(this).is(':checked')) {
                helpdeskQuery1Value = ($(this).data("name"));
            }
        });
        helpdeskQuery(helpdeskQuery1Value ? helpdeskQuery1Value : GetSelectedRadioValue('custService'), $('label[for=' + GetSelectedRadioValue('Tabs') + ']')[0].innerHTML);
    }

    return true;
}

function GetSelectedRadioValue(elementName) {
    var radioValues = document.getElementsByName(elementName);
    var radioValue;
    for (var i = 0; i < radioValues.length; i++) {
        if (radioValues[i].checked) {
            radioValue = radioValues[i].value;
            return radioValue;
        }
    }
}
