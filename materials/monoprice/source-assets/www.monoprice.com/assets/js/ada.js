/* All ADA Compliance Javascript Code */

/* TICK-ADA-43 */
var firstTab = 0;
$("#keyword").change(function () {
    $(".hawk-sqItem").attr("tabindex", "0");
    $(".hawk-sqItem:first").focus();
});
/* TICK-ADA-45 */
$("#bootbox-close-button").click(function () {
    $(".hawknotify-me[data-pid='" + $("#notifypid").val() + "']").focus();
});
$("#hawk-notify-cancel").click(function () {
    $(".hawknotify-me[data-pid='" + $("#notifypid").val() + "']").focus();
});
$(".hawknotify-me").click(function () {
    $(".bootbox-close-button").focus();
    return false;
});
$(".hawk-notify-cancel").focusout(function () {
    $(".bootbox-close-button").focus();
    return false;
});

$("#TTtraWindowClose").click(function () {
    $("#TT3AmqLink").attr('tabindex', '111');
    $("#TT3AmqLink").remove();
});

$(".featherlight-close").click(function () {
    $("#mono4carousel").focus();
});
jQuery(function ($) {
    $('.js-clear-all-items').click(function () {
        $(".mpi-modal-confirm-cancel").attr("tabindex", "0");
        $(".mpi-modal-confirm-confirmed").attr("tabindex", "0");
        $(".mpi-modal-confirm-cancel").focus();
        $(document).on('focus', ".mpi-modal-confirm-cancel", function () {
            // something
        }).on('blur', ".mpi-modal-confirm-cancel", function () {
            // something
        });
    });
});

jQuery(function ($) {
    $('.js-clear-all-items').keydown(function (e) {
        if (e.which == 13) {
            $(this).trigger("click");
            return false;
        }
    });
});
$(".mpi-modal-confirm-cancel").click(function () {
    $(".js-clear-all-items:first").attr("tabindex", "0");
    $(".js-clear-all-items:first").focus();
});
$("#acctBtn").keypress(function (e) {
    if (e.which == 13) {
        $(".my-acct-dropdown").toggleClass("active");
        return false;
    }
});

$("#quickOrder").keypress(function (e) {
    if (e.which == 13) {
        $(".quick-order-dropdown").toggleClass("active");
        return false;
    }
});

$("#myCart").keypress(function (e) {
    if (e.which == 13) {
        $(".mycart-dropdown").toggleClass("active");
        return false;
    }
});

$("#shopBtn").keypress(function (e) {
    if (e.which == 13) {
        $(".shop-dropdown").toggleClass("active");
        return false;
    }
});
$("#featBtn").keypress(function (e) {
    if (e.which == 13) {
        $(".brands-nav").toggleClass("active");
        return false;
    }
});

/* TICK-ADA-48 */
$(document).ready(function () {
    $(".megamenu-sub ul").prop('tabindex', -1);
    $(".megamenu-sub li").prop('tabindex', -1);
});

/* TICK-ADA-50,TICK-ADA-43 */
$(document).keyup(function (e) {
    if (e.keyCode === 27) {
        $(".modal").hide();
        $(".modal-backdrop").hide();
        $("#TTtraBackOverlay").hide();
        $("#TTtraWindow").hide();
        $(".TTui-widget-overlay").hide();
        $("#TTpartnerRegWindow").remove();
        $(".mpi-modal-confirm-cancel").trigger("click");
        $(".hawk-volumepricing-tooltip-content").removeClass("active");
        $(".volume-pricing").css("display", "none");
        $(".submenu").css("display", "none");
    }
});
//$("a").keypress(function (e) {
//    if (e.which == 13) {
//        e.preventDefault();
//        $(this).trigger("click");
//    }
//});
$(document).ready(function () {
    $('.shop-dropdown li').each(function () {
        $(this).attr("tabindex", "0");
    });
    $('.megamenu-sub li').each(function () {
        $(this).removeAttr("tabindex");
    });
    $('.shop-dropdown > li').each(function () {
        $(this).removeAttr("tabindex");
    });
    $('.shop-dropdown > li > a').keyup(function (e) {
        var keyCode = e.keyCode || e.which;

        if (keyCode == 9) {
            $(".megamenu-sub").css("display", "none");
            $(this).parent().find(".megamenu-sub").css("display", "block");
        }
    });
    $(".shop-title").focus(function () {
        $(".megamenu-sub").removeAttr("style");
    });
    $('.shop-dropdown > li > a').focus(function () {
        $("#featBtn").attr("tabindex", "0");
    });
    $(".shop-dropdown a").keyup(function (e) {

        var code = (e.keyCode ? e.keyCode : e.which);
        if (code == 40) {
            $(this).parent().next("li").find("a.desktop-category").focus();
        }
        if (code == 39) {
            $(this).next().next().find("a:first").focus();
        }
        if (code == 38) {
            $(this).parent().prev("li").find("a.desktop-category").focus();
        }
    });
    $(".megamenu-sub a").keyup(function (e) {
        var code = (e.keyCode ? e.keyCode : e.which);
        if (code == 37) {
            $(this).parent().parent().parent("li").find("a.desktop-category").focus();
            $(this).parents('div').parent("li").find("a.desktop-category").focus();
        }
    });
    //$(".shop-dropdown > li > a").focusout(function (e) {        
    //    console.log($(this).parent().next("li").find("a.desktop-category").text());
    //    if ($(this).parent().is(':last-child')) {
    //        $(".megamenu-sub").css("display", "none");
    //        $(".shop-dropdown").removeClass("active");
    //        $("#featBtn").focus();
    //    }
    //    else {
    //        $(this).parent().next("li").find("a.desktop-category").focus();
    //    }
    //});
});
/* TICK-ADA-53 */
$(".nav-tabs li").click(function () {
    $(".nav-tabs li a").attr("aria-selected", "false");
    $(this).find("a").attr("aria-selected", "true");
});

$(".infotabs  li").click(function () {
    $(".infotabs li a").attr("aria-selected", "false");
    $(this).find("a").attr("aria-selected", "true");
});
/* TICK-ADA-55 */
//$(".infotabs li:nth-child(1)").attr("tabindex", "0");
//$(".infotabs li:nth-child(2)").attr("tabindex", "1");
//$(".infotabs li:nth-child(3)").attr("tabindex", "2");
//$(".infotabs li:nth-child(4)").attr("tabindex", "3");
//$(".go-top").attr("tabindex", "4");
////ADA-15-SkippingRepetitiveLinks
//$(window).keyup(function (e) {
//    var code = (e.keyCode ? e.keyCode : e.which);
//    if (code == 9 && window.location.href.indexOf("mp-page-content") == -1) {
//        $(".skip").fadeIn(1000);
//        if (firstTab == 0) {
//            $("#smain").focus();
//            firstTab = 1;
//        }
//    }
//    if (code == 27) {
//        $(".shop-dropdown").removeClass("active");
//        $(".megamenu-sub").css("display", "none");
//        $(".brands-nav").removeClass("active");
//    }
//});
//$(document).on('click', '.skip a', function (e) {
//    $(".skip").fadeOut(1000);
//    $(".skip").hide();
//});
//$(document).on('click', '.skip a', function (e) {
//    $(".skip").hide();
//});
///* TICK-ADA-15 */
//if ($(".skip").length > 0) {
//    $(".skip:not(:first)").remove();
//}
/* TICK-ADA-20 */
$(function () {
    var nodes = document.getElementsByTagName('a');

    for (i = 0; i < nodes.length; i++) {
        if ($(nodes[i]).hasAttribute(name) && $(nodes[i]).text() != "") {
            $(nodes[i]).attr("tabindex", "0");
        }
    }
});
/* TICK-ADA-33 */
$(document).ready(function () {


});
/* TICK-ADA-33 */
$(document).ready(function () {
    $("input").each(function (index) {

        if ($(this).attr("class") != "zipchange" && !$(this).attr("title") && $(this).attr("id") != "input-signup-email") {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
    $("select").each(function (index) {
        if (!$(this).attr("title")) {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
    $("textarea").each(function (index) {
        if (!$(this).attr("title")) {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
});
window.onerror = function (errorMsg, url, lineNumber) {
    console.log('Error: ' + errorMsg + ' Script: ' + url + ' Line: ' + lineNumber);
    $("input").each(function (index) {
        if ($(this).attr("class") != "zipchange" && !$(this).attr("title") && $(this).attr("id") != "input-signup-email") {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
    $("select").each(function (index) {
        if (!$(this).attr("title")) {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
    $("textarea").each(function (index) {
        if (!$(this).attr("title")) {
            var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class");
            $(this).attr("title", data);
        }
    });
}
$("#input-signup-email").removeAttr("title");
//ADA19 PlaceholderValues
$("input").each(function (i, val) {
    if ($(this).attr("placeholder") != null) {
        var id = ($(this).attr("id") != null) ? $(this).attr("id") : '';
        if (!$(this).prev().hasClass('screen-reader-text') && !$(this).prev().is('label')) {
            $(this).before("<label for='" + id + "' class='screen-reader-text' style='display:none;'>" + $(this).attr("placeholder") + "</label>");
        }
    }
});
/* ADA-3 */
$("img").each(function () {
    if (!$(this).attr("alt")) {
        $(this).attr("alt", "");
    }
});
/* ADA-114 */
$("#MasterPassPayButton").keypress(function (e) {
    if (e.which == 13) {
        $("#MasterPassPayButton").trigger("click");
    }
});
$("#AmazonPayButton").keypress(function (e) {
    if (e.which == 13) {
        $("#AmazonPayButton img").trigger("click");
    }
});
//ADA-5-ValidLabel

//$("*").keypress(function (e) {
//    if (e.which == 13) {
//        $(this).trigger("click");
//    }

//});
//$("*").keydown(function (e) {
//    if (e.which == 9) {
//        $(this).trigger("focus");
//    }

//});
//$("*").keyup(function (e) {
//    if (e.which == 9) {
//        $(this).trigger("focusout");
//    }
//});

//$(function () {
//    var nodes = document.getElementsByTagName('*');

//    for (i = 0; i < nodes.length; i++) {

//        if ($(nodes[i]).text() != "") {
//            $(nodes[i]).attr("tabindex", "0");
//        }

//    }
//});
$(document).ready(function () {
    $('.shop-dropdown li').focus(function () {

        if ($(this).attr('role') == "menuitem") {

            var catid = $(this).find("a:first").attr("id");
            if ($(this).find(".megamenu-sub").attr("data-catid") == catid) {
                $(".megamenu-sub").css("display", "none");
                $(this).find(".megamenu-sub").css("display", "block");

            }
        }

    });

    // Hover on Shop Drop down with half second delay - Ashish
    var $menu = $("ul.shop-dropdown");
    // jQuery-menu-aim: Hook up events to be fired on menu row activation.         
    $menu.menuAim({
        activate: activateSubmenu,
        deactivate: deactivateSubmenu
    });

    function activateSubmenu(row) {
        var $row = $(row);
        setTimeout(function () {
            if ($(window).width() > 1215) {
                if ($row.is(":hover")) {
                    $row.find('.megamenu-sub').css({
                        display: "block",
                    });
                }
            }
        }, 500);
    }

    function deactivateSubmenu(row) {
        var $row = $(row);
        setTimeout(function () {
            if ($(window).width() > 1215) {
                $row.find('.megamenu-sub').css("display", "none");
            }
        }, 500);
    }

    $(document).click(function () {
        if ($(window).width() > 1215) {
            $(".megamenu-sub").css("display", "none");
        }
    });

    $(".megamenu-sub").mouseleave(function (event) {
        //this is the original element the event handler was assigned to - Ashish
        var e = event.toElement || event.currentTarget;
        if (e.parentNode == this.parentElement || e == this) {
            return;
        }
        else {
            if ($(window).width() > 1215) {
                $(".megamenu-sub").hide();
            }
        }

        $menu.menuAim({
            activate: activateSubmenu,
            deactivate: deactivateSubmenu
        });
    });

    $("ul.shop-dropdown").mouseleave(function (e) {
        if ($(window).width() > 1215) {
            $menu.menuAim({
                activate: activateSubmenu,
                deactivate: deactivateSubmenu
            });
        }
    });
});
$(".megamenu-sub ul").prop('tabindex', -1);
$(".megamenu-sub li").prop('tabindex', -1);

$(document).ready(function () {
    $(".volume-hover").attr("tabindex", "0");
    $(".volume-hover").keydown(function (e) {
        if (e.which == 13) {
            $(this).find(".volume-pricing").css("display", "block");
        }
    });

    $(".fa-question-circle").focus(function () {
        $(this).hover();
    });
    $(".hawk-volumepricing-tooltip").keypress(function (e) {
        if (e.which == 13) {
            $(this).next().next().addClass("active");
        }
    });

});
/* ADA-12 */
$(document).ready(function () {
    $('body').on('click', '.img-responsive', function () {
        if ($(".setUrl").length >= 0) {
            $(".featherlight-content").attr("tabindex", "0");
            $(".featherlight-content").find(".featherlight-previous").attr("role", "button");
            $(".featherlight-content").find(".featherlight-previous").attr("aria-label", "Previous Slide");
            $(".featherlight-content").find(".featherlight-next").attr("role", "button");
            $(".featherlight-content").find(".featherlight-next").attr("aria-label", "Next Slide");
            $(".featherlight-content").find(".featherligh-close").attr("role", "button");
            $(".featherlight-content").find(".featherligh-close").attr("aria-label", "Close");
            $(".featherlight-content").css('outline', '1px dotted #000');
            $(".featherlight-content").css('overflow', 'hidden');
            $('.featherlight-content').bind({
                focus: function () {

                    $(".featherlight-content").css('border', '1px dotted #000');
                    $(".featherlight-content").css('overflow', 'hidden');
                }
            });
        }
    });
});
$(".hawk-volumepricing-tooltip").focus(function () {
    $(".hawk-volumepricing-tooltip").trigger("mouseenter");
});
$(".hawknotify-me").click(function () {
    $("#hawk_qty").focus();
});
/* TICK-ADA-18 */
$(".TT4addAnswer").click(function () {
    var t = this;
    $(".TT4addAnswer").attr("aria-expanded", "false");
    if (!$('.TT3answersBlock:visible').length == 0) {
        $(this).attr("aria-expanded", "true");
    }
});

$(".TT3add").click(function () {
    if (!$('.TT3added:visible').length == 0) {
        $('.TT3added:visible').find(".TT3addedText").html('<span class="sr-only">Selected</span>');
    }
});
$("li").hover(function () {
    if ($(this).attr("role") == "menuitem") {
        $("li").find("a").attr("aria-expanded", "false");
        $(this).find("a").attr("aria-expanded", "true");
    }
});
$(".hawkFacet-active a").append('<span class="sr-only"> Selected </span>');
var observeDOM = (function () {
    var MutationObserver = window.MutationObserver || window.WebKitMutationObserver,
        eventListenerSupported = window.addEventListener;

    return function (obj, callback) {
        for (i = 0; i < obj.length; i++) {
            try {
                if (MutationObserver) {
                    // define a new observer
                    var obs = new MutationObserver(function (mutations, observer) {
                        if ((mutations[0].addedNodes.length || mutations[0].removedNodes.length) && mutations[0].target.localName != "body" && mutations[0].target.localName != "html" && mutations[0].target.localName != "head") {
                            var ret = (mutations[0].target.id == "") ? "qwer" : mutations[0].target.id;
                            if ($(mutations[0].target.localName)) {
                                if (mutations[0].target.className == "" || ($(mutations[0].target.localName).is('#' + ret))) {
                                    if (mutations[0].target.id == "" || ($(mutations[0].target.localName).is('#' + ret))) {
                                        if ($(mutations[0].target.localName).is('div', 'span')) {
                                            //  $(mutations[0].target.localName).attr('role', 'region');
                                        }
                                        else if ($(mutations[0].target.localName).is('img')) {
                                            $.each($(mutations[0].target.localName), function (index, value) {
                                                var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).attr("class") ? $(this).attr("class") : $(this).text();
                                                if (!$(this).attr('alt')) {
                                                    $(this).attr('alt', data);
                                                    $(this).attr('role', 'img');
                                                }
                                            });
                                        }
                                        else if ($(mutations[0].target.localName).is('a')) {
                                            $.each($(mutations[0].target.localName), function (index, value) {
                                                var data = $(this).attr("placeholder") ? $(this).attr("placeholder") : $(this).attr("data-tooltip") ? $(this).attr("data-tooltip") : $(this).attr("alt") ? $(this).attr("alt") : $(this).attr("name") ? $(this).attr("name") : $(this).attr("value") ? $(this).attr("value") : $(this).text();
                                                if (!$(this).attr('title')) {
                                                    $(this).attr('title', data);
                                                }
                                            });
                                        }

                                    }
                                }
                            }



                        }
                        callback();
                    });
                    // have the observer observe foo for changes in children

                    obs.observe(obj[i], { attributes: true, childList: true, characterData: true });

                }
                else if (eventListenerSupported) {
                    obj[i].addEventListener('DOMNodeInserted', callback, false);
                    obj[i].addEventListener('DOMNodeRemoved', callback, false);
                }
            }
            catch (err) {
                console.log(err);
            }
        }
    };
})();
$("span").each(function () {
    if ($(this).hasClass("color-attr")) {
        $(this).attr("title", $(this).text());
    }
});
// Observe a specific DOM element:
$(document).ready(function () {
    observeDOM(document.getElementsByTagName('*'), function () {

    });
});

$("span").each(function () {
    if ($(this).hasClass("color-attr")) {
        $(this).attr("title", $(this).text());
    }
});
$(document).ready(function () {
    $(".size-attr").each(function () {
        $(this).attr("title", $(this).text());
    });
    $(".size-attr").hover(function () {
        $(this).attr("title", $(this).text());
    });
});

$("#myTab li").each(function () {
    $(this).find("span").attr("title", $(this).text());
});
/* ada-35 */
$(document).ready(function () {

    if ($(".n-prod-section table").find("th").length == 0) {
        $($(".n-prod-section table").find("tr:first").find("td")).each(function () {
            var id = ($(this).attr('id') != "undefined") ? "id='" + $(this).attr('id') + "'" : "";
            var classd = ($(this).attr('class') != "undefined") ? "class='" + $(this).attr('class') + "'" : "";
            $(this).replaceWith('<th ' + id + ' ' + classd + '>' + $(this).html() + '</th>');
        });
    }

});
/* TICK-ADA-36 */
$(".setUrl").click(function () {
    $(".featherlight-content").attr('role', 'dialog');
});
$(document).ready(function () {
    $('body').on('keydown', '.remove-item-cart', function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });
    $(".hawkcolor-image a").removeAttr("tabindex");
    $(".cart-section .size-attr").each(function () {
        $(this).attr("tabindex", "0");
    });
    $(".cart-section .color-attr").each(function () {
        $(this).attr("tabindex", "0");
    });
    $("#hawkitemlist .mp-hawksearch-attrlist .size-attr").removeAttr("tabindex");
    $("#hawkitemlist .mp-hawksearch-attrlist .color-attr").removeAttr("tabindex");

    $(".color-attr").on("keydown", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });
    $(".size-attr").on("keydown", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });

});
$(document).ready(function () {

    $(document).ajaxSuccess(function () {
        $(".cart-section .size-attr").each(function () {
            $(this).attr("tabindex", "0");
        });
        $(".cart-section .color-attr").each(function () {
            $(this).attr("tabindex", "0");
        });
        $(".size-attr").each(function () {
            if ($(this).hasClass("selected")) {
                $(this).attr("title", $(this).attr("data-mp-attrval") + " - Selected");
            }
            else {
                $(this).attr("title", $(this).attr("data-mp-attrval"));
            }
        });
        $(".color-attr").each(function () {
            if ($(this).hasClass("selected")) {
                $(this).attr("title", $(this).attr("data-mp-attrval") + " - Selected");
            }
            else {
                $(this).attr("title", $(this).attr("data-mp-attrval"));
            }
        });
        $("a").each(function () {
            if (!$(this).attr("role")) {
                $(this).attr("role", "link");
            }
        });
        $("button").each(function () {
            if (!$(this).attr("role")) {
                $(this).attr("role", "button");
            }
        });

    });

    $(".color-attr").on("click", function () {
        $(this).trigger("click");
    });
    $(".size-attr").on("click", function () {
        $(this).trigger("click");
    });

    $(".enterpageno").keyup(function (e) {
        if (parseInt($(this).attr("max")) < parseInt($(this).val())) {
            e.preventDefault();
            var $myInput = $(this);
            $myInput.val($myInput.val().slice(0, -1));
        }
    });

    $(".mp-search").click(function () {
        $(this).addClass("open");
        return false;
    });
    $(".close-icon").click(function () {
        $("#keyword").val("");
        $(this).hide();
        $("#keyword").focus();
        return false;
    });
    if ($("#keyword").val() == "") {
        $(".close-icon").hide();
    }
    else {
        $(".close-icon").show();
    }

    $('#keyword').on('input keyup', function (e) {

        if ($(this).val() == "") {
            $(".close-icon").hide();
        }
        else {
            $(".close-icon").show();
        }
    });

    /* TICK-ADA-7 */
    $(".left.carousel-control").find(".sr-only").text("Previous Slide");
    $(".right.carousel-control").find(".sr-only").text("Next Slide");
    /* TICK-ADA-16 */
    $("#keyword").change(function () {
        $(".hawk-autoTerms li").attr("role", "link");
        $(".hawk-autoTerms li").attr("tabindex", "0");
        $(".hawk-autoProducts li").attr("role", "status");
        $(".hawk-autoProducts li").attr("aria-live", "polite");
        $(".hawk-autoProducts li").attr("tabindex", "-1");
    });
    $(".featherlight-close-icon").attr("aria-label", "Close");
});

$(document).ready(function () {
    var nodes = document.getElementsByTagName('*');
    for (i = 0; i < nodes.length; i++) {
        if ($(nodes[i]).attr('data-toggle')) {
            $(nodes[i]).attr('role', $(nodes[i]).attr('data-toggle'));
        }
        if ($(nodes[i]).is('li')) {
            if ($(nodes[i]).attr('data-url')) {
                $(nodes[i]).attr('role', 'link');
            }
            if ($(nodes[i]).attr('aria-label')) {
                $(nodes[i]).attr('role', 'button');
            }
        }
        if ($(nodes[i]).is('div') || $(nodes[i]).is('span')) {
            var events = $._data(nodes[i], "events");
            if (events != null) {
                var hasEvents = (events.click != null);
                if (hasEvents == true) {
                    //  $(nodes[i]).attr('role', 'button');
                }
            }
        }
        else {
            if ($(nodes[i]).attr('title')) {

            }
            else {
                var data = $(nodes[i]).attr("placeholder") ? $(nodes[i]).attr("placeholder") : $(nodes[i]).attr("data-tooltip") ? $(nodes[i]).attr("data-tooltip") : $(nodes[i]).attr("alt") ? $(nodes[i]).attr("alt") : $(nodes[i]).attr("name") ? $(nodes[i]).attr("name") : $(nodes[i]).attr("value") ? $(nodes[i]).attr("value") : $(nodes[i]).attr("class") ? $(nodes[i]).attr("class") : $(nodes[i]).text();
                //  $(nodes[i]).attr('title', data);
            }
        }
    }
});
/* TICK-ADA-36 */
$(".setUrl").click(function () {
    $(this).append('<span class="sr-only"> - Opens a dialog</span>');
    $(".featherlight-content").attr('role', 'dialog');
});
/* TICK-ADA-30 */
$("#QuestionsandAnswers").find("#TT3AmqLink").append('<span class="hidden"> - Opens a dialog </span>');
$("#QuestionsandAnswers").find("#TT3MyQALink").append('<span class="hidden"> - Opens a dialog </span>');
/* TICK-ADA-38 */
$(".hawk-railNavHeading").replaceWith("<h2><div class='hawk-railNavHeading'>" + $(".hawk-railNavHeading").html() + "</div></h2>");

/* TICK-ADA-41 */
(function (d) {
    var interval;

    function check() {
        var elm_id;
        if (d.getElementById("TTpartnerRegWindow")) {

            elm_id = d.getElementById("TTpartnerRegWindow");
            elm_id.focus();
            clearInterval(interval);
        }
    }
    interval = setInterval(check, 100); // duration: 100ms
}(document));


$(".hawknotify-me").click(function () {
    $("#bootbox-close-button").focus();
});
/* TICK-ADA-47 */
$("#carouselButtons").attr("tabindex", "0");
$(".carousel-indicators").attr("tabindex", "0");
/* TICK-ADA-169 */
$('#user-menu li').keydown(function (e) {
    var key = e.which;
    if (key == 13) {
        $("#user-menu a").next("ul").css("display", "none");
        $(this).find("a").next().css("display", "block");
        return false;
    }
});

/* TICK-ADA-170 */
/* ADA-175 */
$(document).ready(function () {

    $("a").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });


    $("#icnshpng").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });

    $("#icnpymnt").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });


    $("#icncnfrm").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });

    $("#icndefault").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });

    $("#icnremove").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });


    $("#icnedit").on("keypress", function (e) {
        var t = this;
        if (e.which == 13) {
            $(t).trigger("click");
        }
    });


    $(".cloned a").attr("tabindex", "-1");
    $(".slick-cloned a").attr("tabindex", "-1");
});


$(document).ready(function () {
    $("a").keydown(function (e) {
        if (e.which == 13 && $(this).attr("href") && $(this).attr("href") != "#") {
            window.location.href = $(this).attr("href");
        }
    });
});
$(document).ready(function () {
    $("#openlist").keypress(function (e) {
        var key = e.which;
        if (key == 13) {
            if ($("#confidencelist").css('display') == 'none') {
                $("#confidencelist").css("display", "block");
            }
            else {
                $("#confidencelist").css("display", "none");
            }
        }
    });

    /* ADA-177 */
    $(".owl-next").attr("role", "arrow");
    $(".owl-prev").attr("role", "arrow");
    $(".owl-dot").attr("role", "button");


    /* TICK-ADA-176 */
    $("a").each(function () {
        if (!$(this).attr("role")) {
            $(this).attr("role", "link");
        }
    });
    $("button").each(function () {
        if (!$(this).attr("role")) {
            $(this).attr("role", "button");
        }
    });

});


/* ADA-181 */
$(document).ready(function () {
    $(".category-menu > ul > li > a").keyup(function (e) {
        var key = e.which;

        var t = this;
        if (key == 9) {
            $(".category-menu ul li").each(function () {
                $(this).removeClass("maintainHover");
                $(this).find(".submenu").css("display", "none");
                $(this).find(".submenu").css("width", "776px");
                $(this).css("background-color", "none");
                $(this).css("border", "none");
            });
            $(t).parent().addClass("maintainHover");
            $(t).parent().css("background-color", "#F8F8F8");
            $(t).parent().css("border-top", "1px solid #c8c8c8");
            $(t).parent().css("border-bottom", "1px solid #c8c8c8");
            $(t).parent().css("border-right", "0px");
            $(t).next(".submenu").css("display", "block");
            $(t).next(".submenu").css("width", "776px");
            $(t).next(".submenu").css("top", "0px");
            $(t).next(".submenu").css("left", "183px");
            $(t).next(".submenu").css("min-height", "601px");
            $(t).next(".submenu").css("max-height", "601px");
            $(t).next(".submenu").css("overflow-y", "auto");
        }
        if (key == 40) {
            $(".category-menu ul li").each(function () {
                $(this).removeClass("maintainHover");
                $(this).find(".submenu").css("display", "none");
                $(this).find(".submenu").css("width", "776px");
                $(this).css("background-color", "none");
                $(this).css("border", "none");
            });
            $(t).parent().next("li").find("a").focus();
            $(t).parent().next("li").addClass("maintainHover");
            $(t).parent().next("li").css("background-color", "#F8F8F8");
            $(t).parent().next("li").css("border-top", "1px solid #c8c8c8");
            $(t).parent().next("li").css("border-bottom", "1px solid #c8c8c8");
            $(t).parent().next("li").css("border-right", "0px");

        }
        if (key == 38) {
            $(".category-menu ul li").each(function () {
                $(this).removeClass("maintainHover");
                $(this).find(".submenu").css("display", "none");
                $(this).find(".submenu").css("width", "776px");
                $(this).css("background-color", "none");
                $(this).css("border", "none");
            });
            $(t).parent().prev("li").find("a").focus();
            $(t).parent().prev("li").addClass("maintainHover");
            $(t).parent().prev("li").css("background-color", "#F8F8F8");
            $(t).parent().prev("li").css("border-top", "1px solid #c8c8c8");
            $(t).parent().prev("li").css("border-bottom", "1px solid #c8c8c8");
            $(t).parent().prev("li").css("border-right", "0px");
        }
        if (key == 39) {
            $(t).parent().addClass("maintainHover");
            $(t).parent().css("background-color", "#F8F8F8");
            $(t).parent().css("border-top", "1px solid #c8c8c8");
            $(t).parent().css("border-bottom", "1px solid #c8c8c8");
            $(t).parent().css("border-right", "0px");
            $(t).next(".submenu").css("display", "block");
            $(t).next(".submenu").css("width", "776px");
            $(t).next(".submenu").css("top", "0px");
            $(t).next(".submenu").css("left", "183px");
            $(t).next(".submenu").css("min-height", "601px");
            $(t).next(".submenu").css("max-height", "601px");
            $(t).next(".submenu").css("overflow-y", "auto");
            $(t).next(".submenu").find("a:first").focus();
        }
    });
});
