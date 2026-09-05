var $spinner = $('<div class="mp-spinner-overlay"><div class="mp-spinner"><i class="fa fa-circle-o-notch fa-spin"></i></div></div>');

mpSpinner = {
    show: function () {
        $("body").append($spinner);
    },
    hide: function () {
        $spinner.remove();
    }
};
$(document).ready(function () {
    $("#orderid").html($("#text-orderid-1").val());
    $("#tracknum").html($("#text-trackid-1").val());
    $("#recievedby").text($("#text-recieveby-1").val());
    $("#deliveredby").text($("#text-delievedby-1").val());
    $(".tabheads").click(function () {
        $(".orderslist-expand").attr("aria-expanded", "false");
        if ($(this).find("i").hasClass("fa-chevron-down")) {
            var id = $(this).attr("class").split(' ')[0].split('-')[1];
            var finalid = "#tabbottom-" + id;
            $(finalid).slideToggle("slow");
            $(this).find("i").toggleClass("fa-chevron-right fa-chevron-down");
        }
        else {
            $(".trackpackage").css("opacity", "0.2");
            $(".tabheads i").removeClass('fa-chevron-down');
            $(".tabheads i").addClass('fa-chevron-right');
            $(".orderslist-expand").slideUp('slow');
            var id = $(this).attr("class").split(' ')[0].split('-')[1];
            var finalid = "#tabbottom-" + id;
            $(finalid).slideToggle("slow");
            $(finalid).attr("aria-expanded", "true");
            $(this).find("i").toggleClass("fa-chevron-right fa-chevron-down");
        }
        setTimeout(
            function () {
                $("#orderid").html($("#text-orderid-" + id).val());
                $("#tracknum").html($("#text-trackid-" + id).val());
                $("#recievedby").text($("#text-recieveby-" + id).val());
                $("#deliveredby").text($("#text-delievedby-" + id).val());
                $(".trackpackage").css("opacity", "1");
            }, 1000);
    });

    $(".tooltiphead").click(function () {
        $(".custom-tooltip").css("display", 'none');
        var id = $(this).attr("class").split(' ')[1].split('-')[1];
        var finalclass = ".tooltipbody-" + id;
        $(finalclass).css("display", 'block');
    });
    $(document).mouseup(function (e) {
        var container = $(".custom-tooltip");

        // if the target of the click isn't the container nor a descendant of the container
        if (!container.is(e.target) && container.has(e.target).length === 0) {
            container.hide();
        }
    });
});
/* Mp-modal */
function cancelpopup(t) {
    if ($(t).attr("data-mp-toggle") == "mp-cancel") {
        var datatarget = $(t).attr("data-mp-target");
        $(datatarget).removeClass("mp-in");
        $(datatarget).css("display", "none");
        $(".mp-modals-backdrop").remove();
        $("body").css("overflow", "auto");
    }
}
$("input,button,a").click(function () {
    $("input[type=button],input[type=submit]").each(function () {
        $(this).attr("title", $(this).attr("value"));
    });
    var RawUrl = "https://images.monoprice.com/productlargeimages/";

    if ($(this).attr("data-mp-toggle") == "mp-modals" && $(this).attr("data-mp-target") == "#myModal") {
        //$("body").append('<div class="mp-spinner-overlay"><div class="mp-spinner"><i class="fa fa-circle-o-notch fa-spin"></i></div></div>');
        $("#accountcart div").remove();
        if ($(this).attr("id") == "buyitagain" && $("[name=productid]:checked").length > 0) {
            $(".checkvalidation").css("display", "none");
            var ids = [];
            var objdata = {};
            var objdata1 = {};
            var t = this;
            var total = 0;
            $("[name=productid]:checked").each(function () {
                ids.push($(this).val());
                objdata[$(this).val()] = $(this).attr("data-usertierprice");
                objdata1[$(this).val()] = $(this).attr("data-oldprice");
            });
            $.ajax({
                url: DomainUrl + "/myaccount/GetProductById", type: 'POST', dataType: 'json', data: JSON.stringify({ 'Ids': ids }), contentType: 'application/json', async: false, success: function (result) {
                    console.log(result);
                    for (var i = 0; i < result.length; i++) {
                        var discount = (parseFloat(objdata[result[i].p_id]) == parseFloat(objdata1[result[i].p_id])) ? "style='display:none !important;'" : "";
                        $("#accountcart").append('<div class="col-md-12" style="padding: 0px 0px 15px 0px;"><div class="mp-col-md-4">' +

                            '<img src="' + RawUrl + result[i].p_id + '1.jpg" style="width: 100px;">' +
                            '</div>' +
                            '<div class="mp-col-md-8">' +
                            ' <h5 tabindex="0">' + result[i].p_name + '</h5>' +
                            ' <p ' + discount + ' style="width: 11%;float:left;">$' + objdata1[result[i].p_id] + '</p>&nbsp;<p style="width: 15%;float:left;color: black;text-decoration: none;">$' + objdata[result[i].p_id] + '</p>&nbsp;<div class="qty-text pull-left" style="clear: both;margin-top: 15px;">' +
                            '<span class="id-icons-qty-label">Qty:</span>' +
                            '<button type="button" class="id-icons minus-' + i + ' minus decreaseqty" title="Decrease Quantity">-</button>' +
                            '<input type="hidden" style="height:33px;" value="' + result[i].p_id + '" class="text-center tpid" size="2" maxlength="5"  name="p_id[]">' +
                            '<input type="hidden" style="height:33px;" value="' + objdata[result[i].p_id] + '" class="text-center tprice price-' + i + '" size="2" maxlength="5"  name="price[]">' +
                            '<input type="text" style="height:33px;" value="1" class="text-center qtyy-' + i + ' qtytextbox" size="2" maxlength="5" id="add-to-cart-qty" name="qty[]">' +
                            '<button type="button" class="id-icons plus-' + i + ' plus increaseqty"  title="Increase Quantity">+</button>' +
                            '</div>' +
                            '  </div></div>');
                        total = parseFloat(total) + parseFloat(objdata[result[i].p_id]);
                        discount = "";
                    }
                    $("#amount").text("$" + total.toFixed(2));
                    //  var position = $(this).position().top;
                    var datatarget = $(t).attr("data-mp-target");
                    // $(".mp-modals-dialog").css("top", position);
                    $(datatarget).addClass("mp-in");
                    $(datatarget).css("display", "block");
                    $("body").append("<div class='mp-modals-backdrop fade in'></div>");
                    $("body").css("overflow", "hidden");
                    $(".mp-spinner-overlay").remove();
                }
            });
        }
        else {
            $(".checkvalidation").css("display", "block");
        }
    }
    else if ($(this).attr("data-mp-toggle") == "mp-modals" && $(this).attr("data-mp-target") == "#myModal1") {
        //  var position = $(this).position().top;
        var datatarget = $(this).attr("data-mp-target");
        var type = $(this).val();
        var typeno = $(this).attr("data-type");
        $(".rmatypedata").val(typeno);
        // $(".mp-modals-dialog").css("top", position);
        $(datatarget).addClass("mp-in");
        $(datatarget).css("display", "block");
        $("body").append("<div class='mp-modals-backdrop fade in'></div>");
        $("body").css("overflow", "hidden");

        $("body").append('<div class="mp-spinner-overlay"><div class="mp-spinner"><i class="fa fa-circle-o-notch fa-spin"></i></div></div>');
        $("#requestitem div").remove();
        $("#requestitem script").remove();
        $.ajax({
            url: DomainUrl + "/myaccount/rmarequest_step1?cmd=" + type + "&order_no=" + $(this).attr("data-orderid"), type: 'GET', success: function (result) {
                $(".mp-spinner-overlay").remove();
                $("#requestitem").html(result);
            }
        });
    }
    else if ($(this).attr("data-mp-toggle") == "mp-modals" && $(this).attr("data-mp-target") == "#myModal2") {
        if ($(this).attr("id") == "writeareview") {
            $(".checkvalidation").css("display", "none");
            $("#prtid").val($(this).attr("data-value"));
            $(".review-pimge").attr("src", $(this).attr("data-image"));
            $(".review-ptitle").text($(this).attr("data-title"));
            $(".review-pid").text($(this).attr("data-value"));
            $("[name=productid]:checked").each(function () {
                $(this).removeAttr("checked");
            });
            //  var position = $(this).position().top;
            var datatarget = $(this).attr("data-mp-target");
            // $(".mp-modals-dialog").css("top", position);
            $(datatarget).addClass("mp-in");
            $(datatarget).css("display", "block");
            $("body").append("<div class='mp-modals-backdrop fade in'></div>");
            $("body").css("overflow", "hidden");
            $(".star1").focus();
        }
        else {
        }
    }
    else if ($(this).attr("data-mp-toggle") == "mp-modals") {
        //  var position = $(this).position().top;
        var datatarget = $(this).attr("data-mp-target");
        // $(".mp-modals-dialog").css("top", position);
        $(datatarget).addClass("mp-in");
        $(datatarget).css("display", "block");
        $("body").append("<div class='mp-modals-backdrop fade in'></div>");
        $("body").css("overflow", "hidden");
    }
    if ($(this).attr("data-mp-target") == "#addlocpayment") {
        $("#locpopup").hide();
        $(".mp-modals-backdrop").remove();
        $("#addlocpayment :input").removeClass("box_exp_err").addClass("form-control");
        $("#addlocpayment div").removeClass("box_exp_err");
        $("#addlocpayment :input").removeClass("box_err").addClass("form-control");
        $("#addlocpayment div").removeClass("box_err");
        $("#addlocpayment :input").removeClass("box_zip_err").addClass("form-control");
        $("#addlocpayment :input").removeClass("box_n").addClass("form-control");
        $("#addlocpayment :input").removeClass("box_zip").addClass("form-control");
        $("#addlocpayment :input").removeClass("box_t").addClass("form-control");

        $("#addlocpayment").find(".mp-submit").removeClass("form-control");
        $("#addlocpayment").find(".mp-cancel").removeClass("form-control");
    }
    if ($(this).attr("data-mp-toggle") == "mp-cancel") {
        var datatarget = $(this).attr("data-mp-target");
        $(datatarget).removeClass("mp-in");
        $(datatarget).css("display", "none");
        $(".mp-modals-backdrop").remove();
        $("body").css("overflow", "auto");
        $(".cleardata").val("");
        $(".cleardata").prop('selectedIndex', 0);
        $(".mp-modals").css("display", "none");
    }
    if ($(this).attr("data-mp-target") == "#addpayment" || $(this).attr("data-mp-target") == "#addpayment") {
        $("input[name='x_card_num']").focus();

    }
    if ($(this).attr("data-mp-target") == "#updateusername") {
        $("#txtfirstname").focus();

    }
    if ($(this).attr("data-mp-target") == "#updatepassword") {
        $("#emailupdate").focus()
    }
    if ($(this).attr("data-mp-target") == "#updateemail") {
        $("input[name='email_address']").focus();
    }
    if ($(this).attr("data-mp-target") == "#emailpreference") {
        $(".origSegPromoEmail").focus();
    }

});
$(document).keyup(function (e) {
    $(".qtytextbox").each(function () {
        $(this).val((isNaN(parseInt($(this).val())) || parseInt($(this).val()) == 0 ? 1 : parseInt($(this).val())));
    });
    recalculate();
    if (e.keyCode === 27) {
        $('.mp-cancel').click();
    }// esc
});
$(document).ready(function () {
    $(".emailaddress").val(Email);
    $(document).on("click", ".increaseqty", function () {
        var id = $(this).attr('class').split(' ')[1].split("-")[1];
        var qty = 0;
        var number = $(".qtyy-" + id).val();
        if (parseInt(number) >= 1) {
            var number = $(".qtyy-" + id).val();
            $(".qtyy-" + id).val(parseInt(number) + parseInt(1));
        }
        else {
            $(".qtyy-" + id).val(1);
        }
        recalculate();
    });
    $(document).on("click", ".decreaseqty", function () {
        var id = $(this).attr('class').split(' ')[1].split("-")[1];
        var number = $(".qtyy-" + id).val();
        if (parseInt(number) <= 1) {
            $(".qtyy-" + id).val(1);
        }
        else {
            $(".qtyy-" + id).val(parseInt(number) - parseInt(1));
        }
        recalculate();
    });
});
function recalculate() {
    var length = $("#accountcart").find(".col-md-12").length;
    var total = 0;
    for (var i = 0; i < length; i++) {
        var price = $(".price-" + i).val();
        var qty = $(".qtyy-" + i).val();
        total = parseFloat(total) + (parseFloat(price) * parseFloat(qty));
    }
    $("#amount").text("$" + total.toFixed(2));
}
/* ----- */

//
// TO-DO: Buy It Again
//
(function ($container, carouselSize) {
    var itemCount = $container.find('.item-list li').length;
    var itemHeight = 150;

    if (itemCount == 0) {
        $container.hide();
        $('.mp-cart-quick-order')
            .css('margin-bottom', 0)
            .find('.handle').trigger('click');
        return;
    }

    if (itemCount <= carouselSize) {
        $container.find('.scroll-up, .scroll-down').hide();
        return;
    }

    var $itemListClone = $container.find('.item-list').clone();
    var index = 0;

    $container.find('.vertical-carousel')
        .css('overflow', 'hidden')
        .css('height', itemHeight * carouselSize)
        .css('position', 'relative');

    // reconstruct items for carousel
    $container.find('.item-list li').remove();
    $container.find('.item-list').append($itemListClone.find('li').last().clone());
    for (var i = 0; i < carouselSize + 1; i++) {
        $container.find('.item-list').append($itemListClone.find('li').eq(i).clone());
    }

    $container.find('.item-list')
        .css('position', 'absolute')
        .css('top', 0)

    $container
        .on('click', '.scroll-down', function () {
            index++;
            var n = (((index + carouselSize) % itemCount) + itemCount) % itemCount;
            $container.find('.item-list').animate({ top: -2 * itemHeight }, 'fast', function () {
                $container.find('.item-list li').first().remove();
                $container.find('.item-list').append($itemListClone.find('li').eq(n).clone());
                $container.find('.item-list').css('top', 0);
            });
        })
        .on('click', '.scroll-up', function () {
            index--;
            var n = ((index % itemCount - 1) + itemCount) % itemCount;
            $container.find('.item-list').animate({ top: 0 }, 'fast', function () {
                $container.find('.item-list li').last().remove();
                $container.find('.item-list').prepend($itemListClone.find('li').eq(n).clone());
                $container.find('.item-list').css('top', 0);
            });
        });
})($('.mp-cart-saved-popular-items'), $('.mp-cart-saved-popular-items').data('carouselSize'));

function func_accountaddtocart(form) {
    var wishListId = $(form).find(".wishlistid").val();
    $("body").append('<div class="mp-spinner-overlay"><div class="mp-spinner"><i class="fa fa-circle-o-notch fa-spin"></i></div></div>');
    var vqty = [];
    var vpid = [];
    var inttquanty = 0;
    $(form).find(".tpid").each(function () {
        vpid.push($(this).val());
    });
    $(form).find(".qtytextbox").each(function () {
        vqty.push($(this).val());
    });
    var data = "";
    for (var i = 0; i < vpid.length; i++) {
        var s = (i == 0) ? "" : i;
        data += "qty" + s + "=" + vqty[i] + "&p_id" + s + "=" + vpid[i] + "&";
        inttquanty += parseInt(inttquanty) + parseInt(vqty[i]);
    }
    var intItemCountHeader = 0;
    var intItemCountHeaderNew = 0;

    var itemCountHeader = $("#top-header-item-count").text();
    if (itemCountHeader != "") intItemCountHeader = parseInt(itemCountHeader, 10);
    var itemCountHeaderNew = $(".checkout__button").text();
    if (itemCountHeaderNew != "") intItemCountHeaderNew = parseInt(itemCountHeaderNew, 10);
    var itemCount = parseInt($("#top-header-item-count").text(), 10);
    var itemCountNew = parseInt($(".checkout__button").text(), 10);
    var intvqty = parseInt(inttquanty, 10);
    if (intvqty > 0) {
        $.ajax({
            type: "POST",
            url: '/cart',
            data: data,
            success: function (result) {
                updateitemcart('');
                $("#myCart").trigger("click");
                if (!$('#monoMini').hasClass('animated')) {
                    $(".mp-spinner-overlay").remove();
                    setTimeout(function () {
                        $('#monoMini').css('display', 'block');
                        var contentheight = $("#monoMiniContent").height() + $("#monoMiniBottom").height();
                        var miniheight = 390;
                        if (contentheight < 390) { miniheight = contentheight + 33; }
                        $('#monoMini').dequeue().stop().animate({ height: miniheight + "px" }, 100);

                        setTimeout(function () {
                            $('#monoMini').addClass('animated').animate({ height: "0" }, 100, function () {
                                $('#monoMini').css('display', 'none');

                                $('#monoMini').removeClass('animated').dequeue();
                            });
                        }, 2000);
                    }, 500);
                }

                itemCount += intvqty;
                itemCountNew += intvqty;

                $("#top-header-item-count").html(itemCount);
                $("#top-header-item-count").focus();
                $(".checkout__button").html('<i class="glyphicon glyphicon-shopping-cart"></i> ' + itemCountNew);
                $("#" + wishListId).remove();
                jQuery(window).scrollTop(0);
                callListrak();

            },
            error: function () {
                return true;
            }
        });
    }

    //
    return false;
}

function callListrak() {
    (function () {
        if (typeof _ltk == 'object') { ltkCode(); } else { (function (d) { if (document.addEventListener) document.addEventListener('ltkAsyncListener', d); else { e = document.documentElement; e.ltkAsyncProperty = 0; e.attachEvent('onpropertychange', function (e) { if (e.propertyName == 'ltkAsyncProperty') { d(); } }); } })(function () { ltkCode(); }); } function ltkCode() {
            _ltk_util.ready(function () {
                /********** Begin Custom Code **********/

                digitalData.cart.forEach(function (item, index) {
                    _ltk.SCA.AddItemWithLinks(item.productID, item.quantity, item.discountedPriceTotal, item.name, item.productImageUrl, item.productPageUrl);
                });
                _ltk.SCA.Submit();

                /********** End Custom Code ************/
            })
        }
    })();
}


$(".delete-address").click(function () {
    $(".appenddetails div").remove();
    var id = $(this).attr("data-value");
    var classValue = "." + id + "-detail";
    $(".appenddetails").html($(classValue).html());
    $("#popup-u_idx").val(id);
});
$(".delete-paymentaddress").click(function () {
    $(".appenddetails1 div").remove();
    var id = $(this).attr("data-value");
    $("#deletepaymentaddress form").attr("action", "/myaccount/deletecreditcard?idx=" + id);
    var classValue = "." + id + "-details";
    $(".appenddetails1").html($(classValue).html());
});
$(".edit-paymentaddress").click(function () {
    $("ul.editselect li").each(function () {
        $(this).find("a").attr("data-toggle", "tab");
    });
    var bill = $(this).attr("data-bill");

    $(".alladdress").removeClass("selected-address");
    $("#pay-info div").remove();
    $("#pay-info a").remove();
    var id = $(this).attr("data-value");

    $("#" + bill + "-selectedaddress").addClass("selected-address");
    $(".selected-address").css("margin", "0px");
    $(".selected-address").prevAll().css("margin", "0px");
    var method = $(this).attr("data-method");
    $("#cc_idx_e").val(id);
    $("#x_paymentmethod_e").val(method);
    $("#editnewaddressp").find('input[name="x_paymentmethod"]').val(method);
    $(".appendbillingaddress1").find('input[name="x_paymentmethod"]').val(method);
    $("#editpayment").find('input[name="cc_idx"]').each(function () {
        $(this).val(id);
    });
    if (method == "Credit Card") {
        $.ajax({
            url: DomainUrl + "/myaccount/SelectUser_CreditCard_ByIdx/?i_cc_idx=" + $(this).attr("data-value") + "&user_id=" + $(this).attr("data-userid"), type: 'GET', dataType: 'json', contentType: 'application/json', async: false, success: function (result) {
                $("#ex_card_num").text("*************" + result.ex_card_num);
                $("#ex_card_num1").val(result.ex_card_num);
                $("#ex_card_name").val(result.ex_card_name);
                $("#eExp_Month").val(result.eExp_Month);
                $("#eExp_Year").val(result.eExp_Year);
                $("#ecs_phone_number").val(result.ecs_phone_number);
            }
        });
    }
    $("ul.editselect li").each(function () {
        var data = $(this).attr("id");
        if (method == data) {
            $(this).find("a").trigger("click");
        }
    });
    $("ul.editselect li").each(function () {
        var data = $(this).attr("class");
        if (data != "active") {
            $(this).find("a").removeAttr("data-toggle");
        }
    });
});
for (var i in countryList) {
    $(".u_country")
        .append($("<option></option>")
            .attr("value", i)
            .text(countryList[i]));
}

for (var i in stateUSList) {
    $(".u_state")
        .append($("<option></option>")
            .attr("value", i)
            .text(stateUSList[i]));
}

for (var i in stateCAList) {
    $(".u_state_ca")
        .append($("<option></option>")
            .attr("value", i)
            .text(stateCAList[i]));
}

$(document).ready(function () {
    $(".qasAddress").blur(function () {
        $("#skip_qas").val("no");
        $("#is_user_overridden").val(false);
    });
});

$(".add-newaddress,.edit-address").click(function () {
    $("input[type=button],input[type=submit]").each(function () {
        $(this).attr("title", $(this).attr("value"));
    });
    $("#u_first_name").focus();
    if ($(this).attr("data-value") == null) {
        $("#mp-title").html("Add New Address");
        $("#addaddress_submit").val("Add New Address");

        if ($("#Country").val() == "US" || $("#Country").val() == "CA") {
            $("#skip_qas").val("no");
        } else {
            $("#skip_qas").val("yes");
        }
    } else {

        $('#UsStates, #CanadaStates, #InternationalStates').hide();
        $.ajax({
            url: DomainUrl + "/myaccount/GetUserAddressByIdQAS/?u_idx=" + $(this).attr("data-value") + "&user_id=" + $(this).attr("data-userid"), type: 'GET', dataType: 'json', contentType: 'application/json', async: false, success: function (result) {
                $("#p-u_idx").val(result.data.u_idx);
                $("#u_first_name").val(result.data.u_first_name);
                $("#u_last_name").val(result.data.u_last_name);
                $("#u_company").val(result.data.u_company);
                $("#skip_qas").val(result.skipQAS);
                var isUserOverridden = false;
                if (result.data.u_overridden != null && result.data.u_overridden) {
                    isUserOverridden = true;
                }
                $("#is_user_overridden").val(isUserOverridden);
                $("#x_ship_to_address").val(result.data.u_address);
                $("#x_ship_to_address2").val(result.data.u_address2);
                $("#Country").val(result.data.u_country);
                $("#x_ship_to_city").val(result.data.u_city);
                if (result.data.u_country == "US") {
                    $("#UsStates").val(result.data.u_state);
                    $("#UsStates").show();
                    $('#Zipcode').attr("maxlength", 10);
                    $('#Zipcode').mask('00000-AAAA');
                    $('#Zipcode').attr("data-mask", "00000-AAAA");
                } else if (result.data.u_country == "CA") {
                    $("#CanadaStates").val(result.data.u_state);
                    $("#CanadaStates").show();
                    $('#Zipcode').attr("maxlength", 7);
                    $('#Zipcode').mask('AAA AAA');
                    $('#Zipcode').attr("data-mask", "AAA AAA");

                } else {
                    $("#InternationalStates").val(result.data.u_state);
                    $("#InternationalStates").show();
                    $('#Zipcode').attr("maxlength", 15);
                    $('#Zipcode').mask('AAAAAAAAAAAAAAA', {
                        translation: {
                            'A': { pattern: /[A-Za-z0-9\s]/ }  // Allows letters, numbers, and spaces
                        }
                    });
                    $('#Zipcode').attr("data-mask", "AAAAAAAAAAAAAAA");
                }
                $("#Zipcode").val(result.data.u_zip);
                if (result.data.u_zip.length == 9 && !isNaN(parseFloat(result.data.u_zip))) {
                    $('#Zipcode').val(function (i, text) {
                        return text.replace(/(\d{5})(\d{4})/, '$1-$2');
                    });
                }
                $("#u_phone").val(result.data.u_phone);
                if (result.data.u_country == "US" || result.data.u_country == "CA") {
                    $('#u_phone').val(function (i, text) {
                        return text.replace(/(\d{3})(\d{3})(\d{4})/, '($1) $2-$3');
                    });
                }
                $("#mp-title").html("Edit Address (" + result.data.u_first_name + " / " + result.data.u_address + ")");
                $("#addaddress_submit").val("Update");
                //$("#title-name").text(result.u_first_name);
                //$("#title-address").text(result.u_address);
            }
        });
    }
})

$(".addselect li").click(function () {
    $(".addselect li").find("input").removeAttr("checked");
    $(this).find("input").prop("checked", true);
    var type = $(this).attr("data-val");
    $(".appendbillingaddress").find('input[name="x_paymentmethod"]').val(type);
    $("#newaddressp").find('input[name="x_paymentmethod"]').val(type);
});
$(".contactus-button").click(function () {
    window.location.href = $(this).attr("data-href");
});

// $('.btn-payment-bgcolor').on("click", function (e) {
// if ($('#creditPayment').val() == "0") {
// if ($(this).attr("data-mp-toggle") == "mp-modals") {
// var datatarget = $(this).attr("data-mp-target");
// $(datatarget).addClass("mp-in");
// $(datatarget).css("display", "block");
// $("body").append("<div class='mp-modals-backdrop fade in'></div>");
// var vv = $("#addressnew");
// $(datatarget).find('#AddAddress').append(vv);
// $(datatarget).find('#AddAddress').find('#addressnew').removeAttr('style');
// $("body").css("overflow", "hidden");
// }

// if ($(this).attr("data-mp-toggle") == "mp-cancel") {
// var datatarget = $(this).attr("data-mp-target");
// $(datatarget).removeClass("mp-in");
// $(datatarget).css("display", "none");
// $(".mp-modals-backdrop").remove();
// $("body").css("overflow", "auto");
// }
// return false;
// }
// });

function js_empty(p_id, str) {
    if (str == "Reason here") {
        eval("document.all.id_etc_reason" + p_id + ".value = ''")
    }
}

function js_etc_reason(p_id, str) {
    if (str == "99") {
        eval("document.all.id_etc_reason" + p_id + ".style.display = 'block'")
    } else {
        eval("document.all.id_etc_reason" + p_id + ".style.display = 'none'")
        eval("document.all.id_etc_reason" + p_id + ".value = 'Reason here'")
    }

    if (str != "") {
        eval("document.rma.rma_chk" + p_id + ".checked = true")
        eval("document.all.rma_tr" + p_id + ".style.backgroundColor = '#e4e4e4'")
    }
}
function js_selected(idx) {
    if (eval("document.rma.rma_chk" + idx + ".checked == true")) {
        eval("document.all.rma_tr" + idx + ".style.backgroundColor = '#e4e4e4'")
    } else {
        eval("document.all.rma_tr" + idx + ".style.backgroundColor = document.rma.rma_bgcolor" + idx + ".value")
    }
}

function js_changed(idx) {
    if (eval("document.rma.rma_quantity" + idx + ".value != 0")) {
        eval("document.rma.rma_chk" + idx + ".checked = true")
        eval("document.all.rma_tr" + idx + ".style.backgroundColor = '#e4e4e4'")
    }
    else {
        eval("document.rma.rma_chk" + idx + ".checked = false")
        eval("document.all.rma_tr" + idx + ".style.backgroundColor = document.rma.rma_bgcolor" + idx + ".value")
    }
}
function checkformRMA(thisform) {
    var chk_num = 0;
    for (var d = 0; d < dp_form.length; d++) {
        if (eval("thisform." + dp_form[d]) == null) {
            return false;
        }
        else {
            if (!eval("thisform." + dp_form[d] + ".length")) {
                if (eval("thisform." + dp_form[d] + ".checked")) {
                    chk_num = chk_num + 1;

                    if (isNaN(eval("thisform." + dp_form1[d] + ".value")) == true) {
                        alert('Please input valid RMA quantity.');
                        eval("thisform." + dp_form1[d] + ".focus()");
                        return false;
                    }
                    if (parseInt(eval("thisform." + dp_form2[d] + ".value")) < parseInt(eval("thisform." + dp_form1[d] + ".value"))) {
                        alert('RMA quantity is more than the quantity you bought.\nPlease input valid RMA quantity.');
                        eval("thisform." + dp_form1[d] + ".focus()");
                        return false;
                    }
                    if (eval("thisform." + dp_form3[d] + ".value") == "") {
                        alert('Please select rma reason!');
                        eval("thisform." + dp_form3[d] + ".focus()");
                        return false;
                    }

                    if (eval("thisform." + dp_form1[d] + ".value") == "" || eval("thisform." + dp_form1[d] + ".value") == "0") {
                        alert('Please input RMA quantity.');
                        eval("thisform." + dp_form1[d] + ".focus()");
                        return false;
                    }
                }
            }
        }
    }
    if (chk_num == 0) {
        alert('Please choose items you want to refund or replacement.');
        return false;
    }

    return true;
}

//$(".zipchange").keypress(function () {
//    var countryclass = "country" + $(this).attr("class").split(' ').pop().split("zip")[1];
//    if ($("." + countryclass).val() == "US") {
//        $(this).attr("maxlength", "5");
//        var found = $(this).val().length;
//        if (found > 5) {
//            $(this).val($(this).val().substr(0, 5));
//        }
//    }
//    else {
//        $(this).attr("maxlength", "6");
//        var found = $(this).val().length;
//        if (found > 6) {
//            $(this).val($(this).val().substr(0, 6));
//        }
//    }
//});

/* Change Addressbook */

/*WP-1733 Removed checkbox values when selecting remove me fromm all emails in Email Preference*/
function unsubscribeCheckBox(isChecked, name) {
    var checkboxes = document.getElementsByTagName("input");
    for (var i = 0; i < checkboxes.length; i++) {
        if (checkboxes[i].name.indexOf(name) == 0) {
            checkboxes[i].checked = false;
            $('.segPromoEmail').val(false);
            $('.segProductReviews').val(false);
            $('.segShoppingReminders').val(false);
        }
    }
}
function updateCheckboxValue(input, name) {
    if ($(input).is(':checked')) {
        $("." + name).val(true);
    }
    else {
        $("." + name).val(false);
    }
}

//unsubscribeCheckBox($(".unsubscribe").attr("checked"), 'origSeg');

$(".selectbilling").click(function () {
    $(".hidebutton").hide();
});
$(".newbilling").click(function () {
    $(".hidebutton").show();
});

$('#pagemove').keypress(function (e) {
    if (e.which == 13) {
        var val = $(this).val();
        move_page(val);
    }
});

$('#pagemove1').keypress(function (e) {
    if (e.which == 13) {
        var val = $(this).val();
        move_page1(val);
    }
});

$(".removecartproduct").click(function () {
    var wishListId = $(this).attr("data-wishid");
    $.ajax({
        url: DomainUrl + "/myaccount/deleteWishlistID/?ID=" + wishListId, type: 'GET', dataType: 'json', contentType: 'application/json', async: false, success: function (result) {
        }
    });
    $("#" + wishListId).remove();
});
$(document).ready(function () {
    $('[data-toggle="tooltip"]').tooltip();

    $("#myTab li").attr("aria-selected", "false");
    $("#myTab li").each(function () {
        var currentLocation = window.location;
        var url = $(this).find("a").attr("href");
        if (currentLocation.toString().indexOf(url.toString()) != -1) {
            $(this).attr("aria-selected", "true");
        }
    });
});
/* Esc Event */
$(document).keyup(function (e) {
    if (e.which == 27) {
        $(".mp-modals").hide();
    }
});
$(document).ready(function () {
    var star = 0;
    $("#cancelreview").click(function () {
        $("[name='rating']").removeAttr("checked");
        star = 0;
    });
    $(".star1").keyup(function (e) {
        $("[name='rating']").removeAttr("checked");
        switch (e.keyCode) {
            case 38: star = star + 1;
                break;
            case 40: star = star - 1;
                break;
            case 39: star = star + 1;
                break;
            case 37: star = star - 1;
                break;
        }
        switch (star) {
            case 6: star = 5;
                break;
            case -1: star = 0;
                break;
        }
        $("[name='rating']").each(function () {
            if (parseInt(star) == parseInt($(this).val())) {
                $(this).attr("checked", "checked");
            }
        });
    });
});
$("button").each(function () {
    $(this).attr("title", $(this).text());
});

$(".titlelink").each(function () {
    $(this).attr("title", $(this).text());
});

//WP-2783- Listrack
$(".edit-preference").click(function () {
    mpSpinner.show();
    ListrakEmailPerferenceCenterEdit();
});
function ListrakEmailPerferenceCenterEdit() {
    var nopreferences = true;
    $.ajax({
        type: "GET",
        url: "/MyAccount/GetContactList",
        success: function (data) {
            $.each(data.ListrakListItem, function (key, value) {
                var listrakFieldId = "#listrakEdit_" + value.ListID;
                if (value.SubscribeStatus.data !=null && value.SubscribeStatus.data.subscriptionState == "Subscribed") {
                    $(listrakFieldId).prop("checked", true);
                    $(listrakFieldId).attr('value', true);
                    nopreferences = false;
                } else {
                    $(listrakFieldId).prop("checked", false);
                    $(listrakFieldId).attr('value', false);
                }
                if (value.ListID == "349731") {
                    if (value.SubscribeStatus.data != null) {
                        $.each(value.SubscribeStatus.data.segmentationFieldValues, function (key1, value1) {
                            var listrakFieldId = "#listrakEdit_" + value1.segmentationFieldId;
                            if (value1.value == "on") {
                                $(listrakFieldId).prop("checked", true);
                                nopreferences = false;
                            }
                        });
                    }
                }
                if ($("#listrakEdit_349731").is(':checked')) {
                    $('.updateinterestlist').attr("disabled", false);
                } else {
                    $('.updateinterestlist').attr("disabled", true);
                }
            });
            $("#unsubscribeall").prop("checked", false);

            if (nopreferences) {
                $("#unsubscribeall").prop("checked", true);
            }
            mpSpinner.hide();
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            $('.listrackErrMsgEdit').show();
            mpSpinner.hide();
        }
    });
}
$("#updateEmailPreference").click(function () {
    mpSpinner.show();
    var listrakData = [];
    $('.updateemaillist').each(function () {
        var listId = $(this).data("val");
        if (listId == "349731") {
            var listrakInterests = [];
            $('.updateinterestlist').each(function () {
                var value = "";
                if (this.checked) {
                    value = "on";
                } else{
                    value = "off";
                }
                var segmentationFieldId = $(this).data("val");
                listrakInterests.push({
                    segmentationFieldId: segmentationFieldId,
                    value: value,
                });
            });
            var isSelected = this.checked;
            listrakData.push({
                ListID: listId,
                IsSelected: isSelected,
                OverrideUnsubscribe: true,
                Segmentations: null
            });

            listrakData.push({
                ListID: listId,
                IsSelected: isSelected,
                OverrideUnsubscribe: true,
                Segmentations: listrakInterests
            });
        }
        else {
            var isSelected = this.checked;
            listrakData.push({
                ListID: listId,
                IsSelected: isSelected,
                OverrideUnsubscribe: true,
                Segmentations: null
            });
        }
    });
    ListrakEmailPerferenceCenterUpdate(listrakData);
});
$("#listrakEdit_349731").click(function () {
    if ($(this).is(':checked')) {
        $('.updateinterestlist').attr("disabled", false);
    } else {
        $('.updateinterestlist').prop("disabled", true);
        $('.updateinterestlist').each(function () {
            $(this).prop("checked", false);
        });
    }
});


$("#unsubscribeall").click(function () {
    $('.updateemaillist').prop("checked", false);
    $('.updateinterestlist').prop("checked", false);
    $('.updateinterestlist').prop("disabled", true);
});
$(".updateemaillist").click(function () {
    $('#unsubscribeall').prop("checked", false);
});
$(".updateinterestlist").click(function () {
    $('#unsubscribeall').prop("checked", false);
});
$("#cancelEmailPreference").click(function () {
    location.reload(true);
});
function ListrakEmailPerferenceCenterUpdate(listrakData) {
    $.ajax({
        type: "POST",
        url: "/MyAccount/CreateUpdateContact",
        data: JSON.stringify({
            listrakSubscriptionFields: listrakData
        }),
        contentType: 'application/json;',
        success: function (data) {
            if (data) {
                location.reload(true);
                mpSpinner.hide();
            } else {
                $('.listraksubscriptions').hide();
                $('#updateEmailPreference').hide();
                $('.listrackErrMsgEdit').show();
                mpSpinner.hide();
            }
        },
        error: function (XMLHttpRequest, textStatus, errorThrown) {
            $('.listrackErrMsgEdit').show();
            mpSpinner.hide();
        }
    });
}
