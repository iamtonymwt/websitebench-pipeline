$(function () {
    $('#CanadaStates, #InternationalStates').hide();
    $('#CanadaStatesBilling, #InternationalStatesBilling').hide();
    $('#CanadaStatesEditBilling, #InternationalStatesEditBilling').hide();

    $("#addaddress_submit").click(function () {
        if ($("#skip_qas").val() == "no") {
            try {
                $("#is_user_overridden").val(false);
                var ValidUSZipcode = false;
                $.ajax({
                    url: "/QAS/ValidZipcodeByState?State=" + $('#UsStates').val() + "&Zipcode=" + $('#Zipcode').val() + "&City=" + $('#x_ship_to_city').val() + "&Country=" + $('#Country').val(),
                    cache: false,
                    success: function (data) {
                        if (data) {
                            ValidUSZipcode = true;
                            $('.zipcodemismatch').hide();
                        }
                        if ($("#Country").val() == "US" && ValidUSZipcode) {
                            qas.verification.QAS_Verify();
                        } else if ($("#Country").val() == "US" && !ValidUSZipcode) {
                            $('.zipcodemismatch').show();
                        } else if ($("#Country").val() == "CA") {
                            qas.verification.QAS_Verify();
                        } else {
                            $("#qas-addaddress-modal").hide();
                            $("#qas-addaddress").show();
                            $("#addaddress").hide();
                            $("#skipqas").val("yes");
                            $("#addressform").submit();
                        }
                    }
                });

                
            } catch (ex) {
                $("#qas-addaddress-modal").hide();
                $("#qas-addaddress").show();
                $("#addaddress").hide();
                $("#skipqas").val("yes");
                $("#addressform").submit();
            }
        } else {
            $("#qas-addaddress-modal").hide();
            $("#qas-addaddress").show();
            $("#addaddress").hide();
            $("#skipqas").val("yes");
            $("#addressform").submit();
        }

    });

    $(document).on('click', '.modal-closebtn', function () {
        $("#qas-addaddress-modal").hide();
        $("#qas-addaddress").show();
    });


    // Added By AShish Loader
    var $mpCktAjaxLoader = $('<div class="mp-ckt-overlay"><i class="fa fa-spin fa-circle-o-notch"></i></div>');

    // Added By Ashish ZipCode Change Function
    $(document).on('change', '#Zipcode', function () {

        var zipcode = $('#Zipcode').val();
        var countryCode = $('#Country').val();
        var upsAgree = false, upsSelected = "UPS", upsAccountNumber = null, b2BAggrementSmIdxSelected = 0;
        var href;

        if (typeof zipcode == "undefined") {
            zipcode = "";
        }

        if ((countryCode == "US" && zipcode.length < 5) || (countryCode == "CA" && zipcode.length < 6)) {
            $("#Zipcode").addClass("error");
            return false;
        } else if (zipcode.length > 0) {
            $("#Zipcode").removeClass("error");
            $("#Zipcode-error").hide();
        }

        $("#Zipcode").focus();
        return false;
    });

    $(document).on('change', '#Country', function () {

        // Added By Ashish for ZipCode Issue
        var selectedCountry = $(this).val();

        // Handle Zipcode field
        $('#Zipcode, input[name="u_zip"]').val('');
        if (window.no_zip_country && window.no_zip_country.indexOf(selectedCountry) >= 0)
            $('#Zipcode, input[name="u_zip"]').hide();
        else
            $('#Zipcode, input[name="u_zip"]').show();

        // Handle State field
        $('#UsStates, #CanadaStates, #InternationalStates').hide();
        $('#UsStates').removeClass("qasAddress");
        $('#CanadaStates').removeClass("qasAddress");
        $('#InternationalStates').removeClass("qasAddress");
        $('#idState').html("State*");

        if (typeof $('#Phone').data('mask') != 'string') {
            $('#Phone').unmask();
        }

        //var selectedCountry = $(this).val();
       // $('#UsStates, #CanadaStates, #InternationalStates').hide();

        switch (selectedCountry) {
        case 'US': // United States
                $('#UsStates').show();
                $('#UsStates').addClass("qasAddress");
                $('#Phone').mask('(000) 000-0000');
            break;
        case 'CA': // Canada
                $('#CanadaStates').show();
                $('#CanadaStates').addClass("qasAddress");
                $('#Phone').mask('(000) 000-0000');
            break;
        default: // International
                $('#InternationalStates').val('').show();
                $('#InternationalStates').addClass("qasAddress");
                //if (window.noStateCountry && window.noStateCountry.indexOf(selectedCountry) >= 0) {
                //    $('#InternationalStates').hide();
                //    $('#idState').html("&nbsp;");
                //} else
                {
                    $('#InternationalStates').show();
                    $('#idState').html("&nbsp;");
                    //$('#idState').html("State*");
                }
                $('#Phone').mask('#');
            return false;
        }
    });
    $(document).on('change', '#BillingCountry', function () {
        var selectedCountry = $(this).val();
        $('#UsStatesBilling, #CanadaStatesBilling, #InternationalStatesBilling').hide();
        switch (selectedCountry) {
            case 'US': // United States
                $('#UsStatesBilling').show();
                break;
            case 'CA': // Canada
                $('#CanadaStatesBilling').show();
                break;
            default: // International
                $('#InternationalStatesBilling').val('').show();
                return false;
        }
    });
    $(document).on('change', '#BillingEditCountry', function () {
        var selectedCountry = $(this).val();
        $('#UsStatesEditBilling, #CanadaStatesEditBilling, #InternationalStatesEditBilling').hide();
        switch (selectedCountry) {
            case 'US': // United States
                $('#UsStatesEditBilling').show();
                break;
            case 'CA': // Canada
                $('#CanadaStatesEditBilling').show();
                break;
            default: // International
                $('#InternationalStatesEditBilling').val('').show();
                return false;
        }
    });
    $(document).on('click', '.keepAddressButton', function () {
        $("#is_user_overridden").val(true);
        $("#qas-addaddress-modal").hide();
        $("#qas-addaddress").show();
        $("#addaddress").hide();
        $("#skipqas").val("yes");
        $("#addressform").submit();
    });
});