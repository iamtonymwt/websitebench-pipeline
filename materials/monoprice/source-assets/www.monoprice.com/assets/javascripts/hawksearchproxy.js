$(document).ready(function () {
    $(".hawk-styleCheckbox").click(function (event) {
        var href = $(this).attr('href');
        href = funcEncodeURL(href);
        location.href = href;
    });
    $(".hawkRemove-NavItems").click(function (event) {
        var href = $(this).attr('href');
        href = funcEncodeURL(href);
        location.href = href;
    });

    $("#idPriceFrom").blur(function () {
        var priceFrom = parseFloat($(this).val());
        var priceTo = parseFloat($("#idPriceTo").val());
        var priceFromOri = $("#idPriceFromOri").val();
        var priceFromFirst = parseFloat($("#idPriceFromFirst").val());
        var href = $("#search-url").val();

        if (priceFrom < priceFromFirst) {
            $("#idPriceFrom").val(priceFromFirst);
        } else {
            js_pricesale_common(priceFrom, priceTo, priceFromOri, "", href);
        }


    });
    $("#idPriceTo").blur(function () {
        var priceFrom = parseFloat($("#idPriceFrom").val());
        var priceTo = parseFloat($(this).val());
        var priceToOri = $("#idPriceToOri").val();
        var priceToFirst = parseFloat($("#idPriceToFirst").val());
        var href = $("#search-url").val();

        if (priceTo > priceToFirst) {
            $("#idPriceTo").val(priceToFirst);
        } else {
            js_pricesale_common(priceFrom, priceTo, "", priceToOri, href);
        }


    });
    $("#mode-grid").click(function () {

        var href = $("#search-url").val();

        location.href = href + "&mode=grid";
    });
    $("#mode-list").click(function () {

        var href = $("#search-url").val();

        location.href = href + "&mode=list";
    });
    $("#mode-grid-bottom").click(function () {

        var href = $("#search-url").val();

        location.href = href + "&mode=grid";
    });
    $("#mode-list-bottom").click(function () {

        var href = $("#search-url").val();

        location.href = href + "&mode=list";
    });

    var $mobileSearchFilter = $('<div id="mobileSearchFilter" class="sb-slidebar sb-left"></div>')
        .append($('.search-filter-container').clone(true));
    $('header').after($mobileSearchFilter);
});


$("#hawk-notify-cancel,#bootbox-close-button").click(function () {

    $("#notifyme").hide();
   
    $("#notifybackdrop").hide();
    $(".notifymodal-right-container").show();
    $(".notifymodal-right-container-message-legal").show();
    $("#notifysubmit").show();
    $(".notifymodal-right-container-message").hide();
    $("#hawk_email_address").val("");
    $("#hawk_qty").val(1);
    $(".error-msg").css("visibility", "hidden");
});

$("#notifysubmit").click(function () {

    var url = "/Product/ProductNotifyMeSubmit"; // the script where you handle the form input.

    if ($("#hawk_qty").val() == "") {  
        $(".error-msg").html('<b>Quantity is Required</b>');
        $(".error-msg").css("visibility", "visible");
        return false;
    }
    if ($("#hawk_email_address").val() == "") {  
        $(".error-msg").html('<b>Email Address is Required</b>');
        $(".error-msg").css("visibility", "visible");
        return false;
    }    
    $.ajax({
        type: "POST",
        url: url,
        data: $("#notify-form").serialize(), // serializes the form's elements.
        success: function (result) {
            $(".notifymodal-right-container").hide();
            $(".notifymodal-right-container-message-legal").hide();
            $("#notifysubmit").hide();
            $(".notifymodal-right-container-message").show();
            $(".notifymodal-right-container-message").focus();
        }       
    });
    return false; // avoid to execute the actual submit of the form.
});

$('.range-slider').jRange({
    from: parseInt($(".hawk-slideRange").attr("data-min-range"), 10),
    to: parseInt($(".hawk-slideRange").attr("data-max-range"), 10),
    step: 1,
    scale: [],
    format: '%s',
    width: 250,
    showLabels: true,
    isRange: true,
    onstatechange: function (value) {
        $('.range-slider').change(js_pricerange(value));
    }
});

function js_pricerange(value) {
    var splitPricesort = value.split(',');
    $("#idPriceFrom").val(splitPricesort[0]);
    $("#idPriceTo").val(splitPricesort[1]);
    $("#id_pricesaleapply").show();
}

function js_pricesaleapply() {
    var priceFrom = parseInt($("#idPriceFrom").val(), 10);
    var priceTo = parseInt($("#idPriceTo").val(), 10);
    var priceFromOri = $("#idPriceFromOri").val();
    var priceToOri = $("#idPriceToOri").val();
    var href = $("#search-url").val();

    js_pricesale_common(priceFrom, priceTo, priceFromOri, priceToOri, href);

}

function js_pricesale_common(vpriceFrom, vpriceTo, vpriceFromOri, vpriceToOri, vhref) {
    if (vpriceFrom > vpriceTo || vhref == "") {
        if (vpriceFromOri != "") $("#idPriceFrom").val(vpriceFromOri);
        if (vpriceToOri != "") $("#idPriceTo").val(vpriceToOri);
    }
    else {
        if (vhref.indexOf("&price_sale") >= 0) {
            var newHref = "";
            var tempHref = vhref.split("&");
            for (i = 0; i < tempHref.length; i++) {
                if (tempHref[i].indexOf("price_sale") < 0) {
                    if (newHref != "") newHref += "&";
                    newHref += tempHref[i];
                }
            }
            vhref = newHref;
        }

        location.href = vhref + "&price_sale=" + vpriceFrom + "," + vpriceTo;
    }
}

function js_notifyme(p_id) {

    document.getElementById("img1").src = "//images.monoprice.com/productmediumimages/" + p_id + "1.jpg";
    document.getElementById("notifypid").value = p_id;

    $("#notifyme").show();
    $("#notifyme").focus();
    $(window).scrollTop($('#notifyme').offset().top);
    $("#notifybackdrop").show();
    $(window).scrollTop($('#notifybackdrop').offset().top);
}

function funcEncodeURL(value) {
    var tempValue = value;
    tempValue = tempValue.split("%2c").join(",");
    tempValue = tempValue.split("%2f").join("/");
    // tempValue = tempValue.split("%26").join("&");

    return tempValue;
}

function func_makeparameter(name, value, parameter) {
    var tempParameter = parameter;

    if (tempParameter != "") {
        var tempParameterTemp = tempParameter + ",";
        if (tempParameterTemp.indexOf(value + ",") >= 0) {
            tempParameterTemp = tempParameterTemp.replace(value + ",", "");
            tempParameter = tempParameterTemp.substring(0, tempParameterTemp.length - 1);
        } else {
            tempParameter += "," + value;
        }
    } else {
        tempParameter = "&" + name + "=" + value;
    }

    return tempParameter;
}

jQuery.fn.ForceNumericOnly =
function () {
    return this.each(function () {
        $(this).keydown(function (e) {
            var key = e.charCode || e.keyCode || 0;
            // allow backspace, tab, delete, enter, arrows, numbers and keypad numbers ONLY
            // home, end, period, and numpad decimal
            return (
                key == 8 ||
                key == 9 ||
                key == 13 ||
                key == 46 ||
                key == 110 ||
                key == 190 ||
                (key >= 35 && key <= 40) ||
                (key >= 48 && key <= 57) ||
                (key >= 96 && key <= 105));
        });
    });
};
$(document).ready(function () {
    if ($(".hawk-selectedHeading").length > 0) {
        $(".hawk-selectedNav").css("display", "block");
    }
});
$(".hawk-navMore1").click(function () {
    var category = "." + $(this).attr("data-category") + "-filter";
    var categorypage = "." + $(this).attr("data-category");
    $(category).find("li").each(function () {
        if ($(this).css('display') == 'none') {
            $(this).removeClass("none");

        }
    });
    $(this).css("display", "none");
    $(categorypage).find(".hawk-navLess1").css("display", "block");
});
$(document).ready(function () {
    $(".hawk-navLess1").click(function () {
        var category = "." + $(this).attr("data-category") + "-filter";
        var categorypage = "." + $(this).attr("data-category");
        $("#mobileSearchFilter").find(category).find("li").each(function (index) {
            if (index > 6) {
                $(this).addClass("none");
            }
            else {
                $(this).removeClass("none");
            }

        });
        $("#mp-page-wrap").find(category).find("li").each(function (index) {
            if (index > 6) {
                $(this).addClass("none");
            }
            else {
                $(this).removeClass("none");
            }

        });
        $(categorypage).find(".hawk-navMore1").css("display", "block");
        $(this).css("display", "none");
    });
    $(".hawk-clearSelected a").removeAttr("onclick");
});
