﻿define([
  'jquery',
  '/assets/js/util/util.js',
  '/assets/js/owl.carousel.js',
  '/assets/js/bootstrap-select.min.js',
  '/assets/js/jquery.mp-responsive-tabs.js',
  '/assets/js/slick.min.js',
  '/assets/javascripts/prod-plugins.js',
  '/assets/js/bootstrap.min.js',
  '/assets/js/plugins/jquery.menu-aim.js',
], function (
    $,
    Util,
    owlCarousel,
    selectpicker,
    responsiveTabs,
    slick
  ) {

    // globals
    var MPI = window.MPI = window.MPI || {};
    var PA = MPI.ProductAttributes = MPI.ProductAttributes || {};
    var allPanels, allLinks;
    var headerOffset = 0;
    var moduleInstance;
    var mpSpinner;

    function View(options) {
        this.options = options || {};
        this.selectors = {
            '$monoCarousel': $('#mono4carousel'),
            '$container': $('#infoPartial'),
            '$imagePartial': $("#imagePartial"),
            '$descPartial': $('#descriptionTab'),
            '$specPartial': $('#specificationsTab'),
            '$btnAddReview': $('.btn-add-review'),
            '$addToCartForm': '.add-to-cart-form',
            '$addToCartBtn': '.btn-add-to-cart',
            '$quantityBtn': '.qty-text .id-icons',
            '$quantityBtn2': '.qty-text-sameline .id-icons',
            '$toggleNotifyBtn': '.btn-module .btn-notify:not(.disabled)',
            '$notifyBtn': '#notifyform .btn-notify',
            '$goToSec': '.go-to-sec',
            '$addReviewBtn': '.btn-add-review',
            '$currPanelSelector': '#accordion .panel-title > a',
            '$spanPlaceholder': 'span.placeholder',
            '$selectFormControl': 'select.form-control',
            '$inputOrTextFormControl': 'textarea.form-control, input.form-control',
            '$addToCartQuantityInput': '#add-to-cart-qty, .qty-input',
            '$mpProdAttrForm': '.mp-prod-attrform',
            '$attrFormBtnDone': '.btn-attrform-done'
        };
    }

    View.prototype.init = function () {
        // base prototype methods
        this.loadProductThumbnails();
        this.setupPageHandlers();
        this.initializeProductAttributes();
        /*Remove sticky cart temporary
        this.initializeStickyCart();*/

        // portable handler methods
        this.handlers.checkWinSize();
        this.handlers.remBtnBorder();
        this.handlers.setupProdCarousel();

        this.initializeSpinner();

        if (this.selectors.$btnAddReview.next('.write-review').hasClass('in')) {
            this.selectors.$btnAddReview.text('Cancel');
        }

        $('span.rating').each(function () {
            this.renderRatingStars($(this), $(this).data('rating'));
        });

        // move this to specific helper
        //$('.infotabs').responsiveTabs(['xs', 'sm']);

    };
    // clean these up for the love of god

    View.prototype.setupPageHandlers = function () {
        $(document).on('click', this.selectors.$goToSec, this.handlers.goToHref.bind(this));
        $(document).on('click', this.selectors.$quantityBtn, this.handlers.updateQuantity.bind(this));
        $(document).on('click', this.selectors.$quantityBtn2, this.handlers.updateQuantity.bind(this));
        $(document).on('click', this.selectors.$notifyBtn, this.handlers.emailFormNotify.bind(this));
        $(document).on('click', this.selectors.$toggleNotifyBtn, this.handlers.toggleNotify.bind(this));
        $(document).on('click', this.selectors.$addReviewBtn, this.handlers.addReview.bind(this));
        $(document).on('click', this.selectors.$currPanelSelector, this.handlers.selectCurrentPanel.bind(this));
        $(document).on('click', this.selectors.$mpProdAttrForm, this.handlers.toggleAttrFlyout.bind(this));
        $(document).on('click', this.selectors.$spanPlaceholder, function () {
            $(this).addClass('hidden');
            $(this).next('input, textarea').focus();
        });

        $(document).on('change', this.selectors.$selectFormControl, this.handlers.hidePlace.bind(this));
        $(document).on('focus', this.selectors.$inputOrTextFormControl, this.handlers.hidePlace.bind(this));
        $(document).on('blur', this.selectors.$inputOrTextFormControl, this.handlers.checkPlaceHolder.bind(this));
        $(document).on('blur', this.selectors.$addToCartQuantityInput, this.handlers.addToCartQuantity.bind(this));

        $(document).tooltip({
            selector: '[data-toggle="tooltip"]'
        });

        $(document).on('submit', this.selectors.$addToCartForm, this.handlers.submitCartForm.bind(this));

        $(window).on('resize load', this.handlers.setupProdCarousel.bind(this));
        $(window).on('resize load', this.handlers.setupCatCarousel.bind(this));
        $(window).on('resize load', this.handlers.selectpickerResize.bind(this));
        $(window).on('resize load', this.handlers.allCollapsePanels.bind(this));
        $(window).on('resize load', this.handlers.eventCheck.bind(this));
        $(window).on('resize', this.initializeProductAttributes.bind(this))
        $(window).on('resize', this.handlers.remBtnBorder, this.handlers.checkWinSize.bind(this));

        /*Remove sticky cart temporary
        $(window).on('load', this.handlers.setupScrollspy.bind(this));
        $(window).on('load', this.handlers.setupAffixElements.bind(this));*/
    };

    // TODO: need to move as much of these out to external modules as possible !!! >:|
    View.prototype.handlers = {

        'goToHref': function (e) {
            var $target = $(e.target),
              offsetTopEle = $target.attr('href'),
              infoH = $('.info-row').outerHeight();

            offsetTop = $(offsetTopEle).offset().top - infoH;

            $('html, body').animate({
                scrollTop: offsetTop
            }, 500);

            return false;
        },

        'updateQuantity': function (e) {
            var $target = $(e.target);
            var qtyCnt = 1,
            qtyVal = $('.qty-text').find('input').val();
            qtyValwithLimit = $('.qty-text-sameline').find('input').val();
             
            if(qtyVal == undefined) 
            {
                if (!isNaN(qtyValwithLimit) && qtyValwithLimit != "") {
                    if ($target.hasClass('minus') && qtyValwithLimit > 1) {
                        qtyCnt = parseInt(qtyValwithLimit) - 1;
                    }
                    if ($target.hasClass('plus')) {
                        qtyCnt = parseInt(qtyValwithLimit) + 1;
                    }
                }
                var a = $('.qty-text-sameline').find('input').val(qtyCnt);
                $('.qty-text').find('input').val(a);
            }
            else
            {
                if (!isNaN(qtyVal) && qtyVal != "") {
                    if ($target.hasClass('minus') && qtyVal > 1) {
                        qtyCnt = parseInt(qtyVal) - 1;
                    }
                    if ($target.hasClass('plus')) {
                        qtyCnt = parseInt(qtyVal) + 1;
                    }
                }
                $('.qty-text').find('input').val(qtyCnt);
            }            
            e.preventDefault();
        },

        'addToCartQuantity': function (e) {
            var $target = $(e.target);
            var qty = $target.val();
            if (isNaN(qty) || qty < 1) {
                $target.val(1);
            }
        },

        'submitCartForm': function (e) {
            e.preventDefault();

            mpSpinner.show();

            if ($(e.target).is(':not(".mp-sticky-cart")')) {
                if (window.func_addtocart) {
                    window.func_addtocart(e.target, function () {
                        mpSpinner.hide();
                    });
                }
            }

            return false;
        },

        'emailFormNotify': function () {
            var emailRegEx = Util.validators.emailValidator().regex,
              emailId = $('.email-input').val(),
              errMsgDiv = $('.notify-frm .error-msg');

            if (!emailId.length) {
                errMsgDiv.text('Email Address is required.');
                return false;
            } else if (!emailRegEx.test(emailId)) {
                errMsgDiv.text('Email Address is invalid.');
                return false;
            }
        },

        'toggleNotify': function (e) {
            var $target = $(e.target);
            $target.toggleClass('active');
            $($target.attr('href')).slideToggle('fast');
            e.preventDefault();
        },

        'checkWinSize': function () {
            return $(window).width();
        },

        'eventCheck': function () {
            if ($('#accordion .extra-added').length && this.handlers.checkWinSize() <= 768) {
                return;
            } else {
                this.handlers.producPageReStructure();
            }
        },

        'producPageReStructure': function () {
            if (this.checkWinSize() <= 768) {
                //$('.extra-added').detach();
                //$('.mobile-accord.hidden').removeClass('hidden');

                //$('.mobile-accord').each(function () {
                //    var mainPanelDiv = $('<div/>').addClass('panel panel-default extra-added'),
                //        panelHeading = $('<div/>').addClass('panel-heading'),
                //        panelTitle = $('<h4/>').addClass('panel-title'),
                //        panelHeadingLink = $('<a/>').addClass('collapsed'),
                //        $this = $(this),
                //        titleText = $this.find('.module-heading').text(),
                //        panelHeadingLinkId,
                //        mainPanelDivId;

                //    panelHeadingLinkId = titleText.replace(/\s+/g, "") + Math.ceil(Math.random() * 10);

                //    if (titleText.indexOf('Reviews') !== -1) {
                //        mainPanelDivId = 'review';
                //        $this.attr('id', 'review-desktop');
                //    }
                //    if (titleText.indexOf('Member Pricing') !== -1) {
                //        mainPanelDivId = 'memberPricing';
                //        $this.attr('id', 'memberPricing-desktop');
                //    }

                //    contents = $this.find('.module-body');
                //    var moduleBody = contents.clone();

                //    var panelCollapse = $('<div/>').addClass('panel-collapse collapse'),
                //        panelBody = $('<div/>').addClass('panel-body extra-added');


                //    $this.addClass('hidden');

                //    panelCollapse.attr({ 'id': panelHeadingLinkId });
                //    if (mainPanelDivId) {
                //        mainPanelDiv.attr({ 'id': mainPanelDivId });
                //    }
                //    panelCollapse.append(panelBody);
                //    panelBody.append(moduleBody);
                //    panelHeadingLink.text(titleText);
                //    panelHeadingLink.attr({ 'href': '#' + panelHeadingLinkId });
                //    panelTitle.append(panelHeadingLink);
                //    panelHeading.append(panelTitle);
                //    mainPanelDiv.append(panelHeading);
                //    $('.panel-group#accordion').append(mainPanelDiv);

                //    mainPanelDiv.append(panelCollapse);

                //});

                //var winIdLocation = window.location.hash;

                //if (winIdLocation) {
                //    var operateDiv = $(winIdLocation),
                //        operateDivTop;

                //    if (!operateDiv.hasClass('panel')) {
                //        operateDiv.closest('.panel-collapse').show();
                //        operateDiv.closest('.panel.extra-added').find('.panel-title a').addClass('collapsed');
                //    } else {
                //        operateDiv.find('.panel-collapse').show();
                //        operateDiv.find('.panel-title a').addClass('collapsed');
                //    }

                //    if (operateDiv.length) {
                //        operateDivTop = operateDiv.offset().top - 70;

                //        $(window).scrollTop(operateDivTop);
                //    }
                //}
                //$('#info-row').hide();
            }
            else {
                //$('.extra-added').detach();
                //$('.panel.panel-default.extra-added').each(function () {
                //    $this = $(this);
                //    var titleText = $this.find('.panel-title a').text();
                //    if (titleText.indexOf('Reviews') !== -1) {
                //        $this.find('#review').removeAttr('id');
                //    }
                //    if (titleText.indexOf('Member Pricing') !== -1) {
                //        $this.find('#memberPricing').removeAttr('id');
                //    }
                //});
                //$(document).find('#review-desktop').attr('id', 'review');
                //$(document).find('#memberPricing-desktop').attr('id', 'memberPricing');
                //$('.mobile-accord.hidden').removeClass('hidden');
                $('#info-row').show();
            }
        },

        'addReview': function (e) {
            var $target = $(e.target);

            if ($target.attr('href') == '#') {
                var writeReviewSec = $target.next('.write-review'),
                    btnText = $target.text();

                if (btnText === 'Cancel') {
                    $target.text('Add your review');
                    writeReviewSec.slideUp('fast');
                } else {
                    $target.text('Cancel');
                    writeReviewSec.slideDown('fast');
                    // clear existing value
                    $('select[name="f_rating"]').val('');
                    $('.filter-option.pull-left').text('');
                    $('input[name="f_title"]').val('');
                    $('textarea[name="f_feedback"]').val('');
                    $('input[name="f_name"]').val('');
                    $('textarea[name="f_pros"]').val('');
                    $('textarea[name="f_cons"]').val('');

                    $('span.placeholder').removeClass('hidden');
                }
            }
        },

        'selectpickerResize': function () {
            if (this.handlers.checkWinSize() <= 768) {
                $('.selectpicker').selectpicker();
                $('.btn-group.bootstrap-select').eq(1).addClass('hidden');

                $('.selectpicker').prev('.placeholder').removeClass('hidden');

            } else {
                $('.selectpicker').selectpicker();

                if ($('.selectpicker').val() === "") {
                    $('.selectpicker').prev('.placeholder').removeClass('hidden');
                } else {
                    $('.selectpicker').prev('.placeholder').addClass('hidden');
                }
            }

            $('.dropdown-menu.inner').find('li').each(function () {
                if ($(this).find('.text').text() === ' ') {
                    $(this).remove();
                }
            });
        },

        'checkPlaceHolder': function () {
            if ($(this).val() !== '') {
                $(this).prev('.placeholder').addClass('hidden');
            } else {
                $(this).prev('.placeholder').removeClass('hidden');
            }
        },


        'allCollapsePanels': function () {
            allPanels = $('#accordion1 .panel-collapse');
            allLinks = $('#accordion1 .panel-title > a');
        },

        'selectCurrentPanel': function (e) {
            var $target = $(e.target);
            var currId = $target.attr('href');

            if (currId.indexOf("Description") >= 0 && IsMobile == "True" && $(currId).is(':hidden')) {

                var $descPartial = $(currId);

                var params = {
                    vals: new Array(),
                    PID: TurnToItemSku,
                    changedVal: $(this).data('mpAttrval'),
                    displayDesc: true
                };
               
                mpSpinner.show();
                $.ajax({
                    type: "GET",
                    url: "/product/selectpid",
                    contentType: "application/json; charset=utf-8",
                    datatype: "json",
                    traditional: true,
                    //data: JSON.stringify(params),
                    data: { vals: params.vals, PID: params.PID, changedVal: params.changedVal },
                    success: function (data) {
                        if (data != null) {
                            if (!data.descPartialView)
                                location.href = '/StaticContent/generalerror';
                            else {
                                $descPartial.html(data.descPartialView);
                                $("h3.fw-bld-700").hide();
                             
                            }
                        }
                    },
                    error: function () {
                        mpSpinner.hide();
                        location.href = '/StaticContent/generalerror';
                    },
                    complete: function () {
                        mpSpinner.hide();
                    }
                });
            }
            allPanels.slideUp('fast');
            allLinks.addClass('collapsed');

            if ($(currId).is(':hidden')) {
                allPanels.slideUp('fast').addClass('collapsed');

                $(currId).slideDown('fast');
                $target.removeClass('collapsed');
            } else {
                $(currId).slideUp('fast');
                $target.addClass('collapsed');
            }
            e.preventDefault();
        },

        'hidePlace': function (e) {
            var $target = $(e.target);
            $target.prev('.placeholder').addClass('hidden');
        },

        'remBtnBorder': function () {
            var $colLength = $('.top-cols').find('.col').length;
            if ($colLength <= 2) {
                $('.top-cols > .col').each(function () {
                    $(this).css({ 'border-bottom': 'none' });
                });
            } else if ($colLength > 2 && $colLength <= 4) {
                $('.top-cols > .col:gt(1)').each(function () {
                    $(this).css({ 'border-bottom': 'none' });
                });
            }
        },

        'setupProdCarousel': function () {
            var productCarousel = $('.prod-carousel'),
                winSize = $(window).width();

            var prodItems = $('.prod-carousel').find('.r-prod').filter(function () {
                return $(this).parent('.cloned').length === 0
            }).length;

            if (productCarousel.data('owlCarousel')) {
                productCarousel.data('owlCarousel').destroy();
                productCarousel.removeClass('owl-carousel owl-hidden owl-loaded').find('.r-prod').unwrap('.owl-stage-outer');
            }

            var owlOpts = {
                loop: true,
                nav: true,
                navText: [
                    "<span class='dir'><i class='fa fa-angle-left'></i></span>",
                    "<span class='dir'><i class='fa fa-angle-right'></i></span>"
                ]
            };

            owlOpts.margin = 20;
            owlOpts.responsive = {
                0: {
                    items: 1
                },
                400: {
                    items: 2
                },
                600: {
                    items: 3
                },
                992: {
                    items: 4
                },
                1090: {
                    items: 5
                }
            };
            owlOpts.mouseDrag = false;

            if (winSize > 0 && winSize <= 400) {
                if (prodItems >= 2) {
                    owlOpts.mouseDrag = true;
                    productCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 401 && winSize < 600) {
                if (prodItems >= 2) {
                    owlOpts.mouseDrag = true;
                    productCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 600 && winSize < 992) {
                if (prodItems > 3) {
                    owlOpts.mouseDrag = true;
                    productCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 992 && winSize < 1090) {
                if (prodItems >= 4) {
                    productCarousel.owlCarousel(owlOpts);
                }
            } else {
                if (prodItems > 5) {
                    productCarousel.owlCarousel(owlOpts);
                }
            }
        },

        'setupCatCarousel': function () {
            var catCarousel = $('.cat-carousel'),
                winSize = $(window).width();

            var catItems = $('.cat-carousel').find('.r-prod').filter(function () {
                return $(this).parent('.cloned').length === 0
            }).length;

            if (catCarousel.data('owlCarousel')) {
                catCarousel.data('owlCarousel').destroy();

                catCarousel.removeClass('owl-carousel owl-hidden owl-loaded').find('.r-prod').unwrap('.owl-stage-outer');
            }

            var owlOpts = {
                loop: true,
                nav: true,
                navText: [
                    "<span class='dir'><i class='fa fa-angle-left'></i></span>",
                    "<span class='dir'><i class='fa fa-angle-right'></i></span>"
                ]
            };

            owlOpts.margin = 20;
            owlOpts.responsive = {
                0: {
                    items: 1
                },
                400: {
                    items: 2
                },
                600: {
                    items: 3
                },
                992: {
                    items: 4
                },
                1090: {
                    items: 5
                }
            };
            owlOpts.mouseDrag = false;

            if (winSize > 0 && winSize <= 400) {
                if (catItems >= 2) {
                    owlOpts.mouseDrag = true;
                    catCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 401 && winSize < 600) {
                if (catItems >= 2) {
                    owlOpts.mouseDrag = true;
                    catCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 600 && winSize < 992) {
                if (catItems > 3) {
                    owlOpts.mouseDrag = true;
                    catCarousel.owlCarousel(owlOpts);
                }
            } else if (winSize >= 992 && winSize < 1090) {
                if (catItems >= 4) {
                    catCarousel.owlCarousel(owlOpts);
                }
            } else {
                if (catItems > 5) {
                    catCarousel.owlCarousel(owlOpts);
                }
            }
        },

        'setupAffixElements': function () {
            var affixElements = {
                '.cart-btns': $($('.cart-btns')[0]),                
                '#info-row': $('#info-row')
            };

            for (var affixElement in affixElements) {
                if (affixElements.hasOwnProperty(affixElement)) {
                    affixElements[affixElement].affix({
                        offset: {
                            top: affixElements[affixElement].offset().top
                        }
                    });
                }
            }
        },

        'setupScrollspy': function () {
            var $staticCartBtns = $($('.cart-btns')[0]),               
              elementSlideSpeed = 250;

            // destroy automatically on open
            $staticCartBtns.off('affix.bs.affix, affix-top.bs.affix, affixed.bs.affix');

            $staticCartBtns.on('affixed.bs.affix', function () {
                $('#mp-page-wrap.sb-site-container').removeClass();
                $('.mp-sticky-cart').css({
                    display: 'block'
                }).stop().animate({
                    top: 0,
                }, elementSlideSpeed);
            });

            $staticCartBtns.on('affix.bs.affix, affix-top.bs.affix', function () {
                $('.mp-sticky-cart').stop().animate({
                    top: -($('.mp-sticky-cart').outerHeight())
                }, elementSlideSpeed, function () {
                    $('.mp-sticky-cart').css({
                        display: 'none'
                    });
                    $('#mp-page-wrap').addClass('sb-site-container');
                });
            });
        },

        'submitReview': function () {
            if ($('select[name="f_rating"] option:selected').val() !== "" && $('input[name="f_title"]').val() !== "" && $('textarea[name="f_feedback"]').val() !== "") {

                $(".review-error").addClass("hidden").find('span').text("");
                $("#review_frm").addClass("hidden");
                $(".inprogress").removeClass("hidden");
                var operateDivTop = $(".inprogress").offset().top - 70;
                $(window).scrollTop(operateDivTop);
                $.ajax({
                    url: 'product/productreviewinsert',
                    data: {
                        p_id: $('input[type=hidden][name="p_id"]').val(),
                        c_id: $('input[type=hidden][name="c_id"]').val(),
                        cp_id: $('input[type=hidden][name="cp_id"]').val(),
                        cs_id: $('input[type=hidden][name="cs_id"]').val(),
                        user_id: $('input[type=hidden][name="user_id"]').val(),
                        f_rating: $('select[name="f_rating"] option:selected').val() * 2,
                        f_title: $('input[name="f_title"]').val(),
                        f_feedback: $('textarea[name="f_feedback"]').val(),
                        f_name: $('input[name="f_name"]').val(),
                        f_pros: $('textarea[name="f_pros"]').val(),
                        f_cons: $('textarea[name="f_cons"]').val(),
                    },
                    type: 'post',
                    success: function (response) {
                        if (response && response != undefined) {
                            if (response.Error == false) {
                                $(".inprogress").addClass("hidden");
                                $(".review-success").removeClass("hidden")
                                .find('span').text(response.Message);

                                $('.btn.btn-add-review').text('Review Submitted').css({ 'cursor': 'default' }).addClass('submitted-btn');
                                operateDivTop = $(".review-success").offset().top - 70;
                                $(window).scrollTop(operateDivTop);
                            } else {
                                $("#review_frm").removeClass("hidden");
                                $(".inprogress").addClass("hidden");
                                $(".review-error").removeClass("hidden").find('span').text(response.Message);
                                operateDivTop = $(".review-error").offset().top - 70;
                                $(window).scrollTop(operateDivTop);
                            }
                        }
                    },
                    error: function () {
                        $("#review_frm").removeClass("hidden");
                        $(".inprogress").addClass("hidden");
                    }
                });
            } else {

                if ($('select[name="f_rating"] option:selected').val() == "") {
                    $(".review-error").removeClass("hidden").find('span').text("Please select Rating.");
                    $('select[name="f_rating"]').addClass('has-error');
                }
                else if ($('input[name="f_title"]').val() == "") {
                    $(".review-error").removeClass("hidden").find('span').text("Please input Review title.");
                    $('input[name="f_title"]').addClass('has-error');
                }
                else if ($('textarea[name="f_feedback"]').val() == "") {
                    $(".review-error").removeClass("hidden").find('span').text("Please input Review feedback.");
                    $('textarea[name="f_feedback"]').addClass('has-error');
                }
            }
        },

        'toggleAttrFlyout': function (e) {
            e.preventDefault();
            var windowWidth = $(window).width();

            if (windowWidth <= 480) {
                $(e.target).toggleClass('active');
            }

        }

    };

    View.prototype.renderRatingStars = function ($el, rating) {
        $el.find('.star').removeClass('active half');
        switch (rating) {
            case 1:
                $el.find('.star:eq(4)').addClass('half');
                break;
            case 2:
                $el.find('.star:eq(4)').addClass('active');
                break;
            case 3:
                $el.find('.star:eq(4)').addClass('active');
                $el.find('.star:eq(3)').addClass('half');
                break;
            case 4:
                $el.find('.star:eq(3)').addClass('active');
                break;
            case 5:
                $el.find('.star:eq(3)').addClass('active');
                $el.find('.star:eq(2)').addClass('half');
                break;
            case 6:
                $el.find('.star:eq(2)').addClass('active');
                break;
            case 7:
                $el.find('.star:eq(2)').addClass('active');
                $el.find('.star:eq(1)').addClass('half');
                break;
            case 8:
                $el.find('.star:eq(1)').addClass('active');
                break;
            case 9:
                $el.find('.star:eq(1)').addClass('active');
                $el.find('.star:eq(0)').addClass('half');
                break;
            case 10:
                $el.find('.star:eq(0)').addClass('active');
                break;
            default:
                $el.find('.star').removeClass('active half');
        }
    };

        View.prototype.loadProductThumbnails = function () {
        var itemNum = $('#mono4carousel').find('.item.lihidable').find('.qtyimgval').attr('value');
        if (itemNum > 4) {
            var owlOpts = {
                nav: true,
                navText: [
                    "<i class='fa fa-angle-left'></i>",
                    "<i class='fa fa-angle-right'></i>"
                ]
            };
            owlOpts.loop = false;
            owlOpts.margin = 0;
            owlOpts.responsive = {
                0: {
                    items: 4
                },
                1090: {
                    items: 4
                }

            };

            $('#mono4carousel').owlCarousel(owlOpts); /* strange bug when refreshing pdp carousel */
            this.selectors.$monoCarousel.on('changed.owl.carousel, initialized.owl.carousel', function (e) {


                if (e.item.count != e.item.index) {
                    this.selectors.$monoCarousel.find('.owl-next').show();
                }

                if (e.item.count === 1) {
                    this.selectors.$monoCarousel.find('.owl-prev').hide();
                } else {
                    this.selectors.$monoCarousel.find('.owl-prev').show();
                }
            });
        }
        //else (itemNum > 0){
        //    $('#mono4carousel').owlCarousel(owlOpts);

        //}

        if ($('.monowrap').find('iframe').length) { // If the first one is the video, choose the second one as default.
            $('.item.lihidable a:eq(1)').find('img').addClass('curr');
        } else {
            $('.item.lihidable a:eq(0)').find('img').addClass('curr');
        }

        this.selectors.$monoCarousel.find('.item.lihidable a').on('click', function (e) {
            var largeImage = $(this).find('.img-thumb').data('largeimg');

            $('.curr').removeClass('curr');

            if (largeImage) {
                $(this).find('img').addClass('curr');

                $(".monowrap .setUrl").attr("href", largeImage);

                $('.monowrap img#mono4').attr({
                    src: largeImage
                }).removeClass('hidden');

                $('#ytVideo').hide();

            } else {
                var videoId = $(this).find('.img-thumb').data('video'),
                    videoSrc = '//www.youtube.com/embed/' + videoId;
                $('#ytVideo').attr({
                    src: videoSrc
                });
                $(this).find('img').addClass('curr');

                $('#ytVideo').show();
                $('img#mono4').attr('src', '').addClass('hidden');
            }

            e.preventDefault();
        });

        // FeatherlightGallery
        $('.lightbox-gallerylist a:eq(0)').removeClass();
        $('a.gallery').featherlightGallery({
            previousIcon: '«',
            nextIcon: '»',
            galleryFadeIn: 300,
            openSpeed: 300,
            afterContent: function () {
                 $('.featherlight-image').attr('alt', $('.setUrl').attr('data-alt'));
            }
        });

    };

    View.prototype.setupProductAttributes = function (windowWidth) {
        var self = this;

        PA.attachEvents = function () {
            $(document).tooltip({
                selector: '.color-attr.outofstock, .color-attr.na, .size-attr.outofstock, .size-attr.na'
            });

            $(document).on('click', '.color-attr, .size-attr', function () {
               
                if ($(this).hasClass('selected'))
                    return false;
                // Toggle selected
                $(this).siblings().each(function () {
                    $(this).removeClass('selected');
                    $(this).children('span.color-val').removeClass('color-selected');
                });
                $(this).addClass('selected');                
                $(this).children('span.color-val').addClass('color-selected');             
                var params = {
                    vals: new Array(),
                    PID: PA.pid,
                    changedVal: $(this).data('mpAttrval')
                };

                $(document).find('.mp-prod-attrform .selected').each(function () {
                    params.vals.push($(this).data('mpAttrval'));
                });

                if (params.vals.length > 2) {
                    params.vals = params.vals.slice(0, params.vals.length);
                }

                self.handleAttributeAjax(params);
               
            });
        }

        PA.init = function () {
            PA.attachEvents();
        }

        $(function () { // run init() on DOM ready
            if (Util.getUrlParameter('notifyme-active') == 'yes') {
                $('#notifyme-btn').click();
            }
            PA.init();
        });
       
    };

    View.prototype.handleAttributeAjax = function (params) {
        var self = this;
        //var pVals = params.vals;
        //var pPid = params.PID;
        //var pchangedVal = params.changedVal;
        mpSpinner.show();
        $.ajax({
            type: "Get",
            url: "/product/selectpid",
            contentType: "application/json; charset=utf-8",
            datatype: "json",
            traditional: true,
            //data: JSON.stringify(params),
            data: { vals: params.vals, PID: params.PID, changedVal: params.changedVal },
            success: function (data) {
                if (data != null) {
                    if (!data.imagePartialView || !data.infoPartialView || !data.descPartialView)
                        location.href = '/StaticContent/generalerror';
                    else {
                        self.selectors.$imagePartial.html(data.imagePartialView);

                        // TurnTo's Speedflex widget binds to the actual #tt-teaser-widget DOM node at
                        // load time; replacing it wholesale (as .html() below does) orphans that
                        // binding and TurnToCmd('set', ...) can no longer repopulate it. Detach and
                        // reinsert the original node so the binding survives the swap.
                        var $teaser = self.selectors.$container.find('#tt-teaser-widget').detach();
                        self.selectors.$container.html(data.infoPartialView);
                        if ($teaser.length) {
                            self.selectors.$container.find('#tt-teaser-widget').replaceWith($teaser);
                        }

                        $('#descriptionTab').html(data.descPartialView);
                        $('#specificationsTab').html(data.specPartialView);

                        if (data.hasDocuments) {
                            $('#documentsTab').html(data.documentsPartialView);
                            $('#documentslist').show();
                        } else {
                            $('#documentsTab').empty();
                            $('#documentslist').hide();
                            if ($('#documentslist').hasClass('active')) {
                                var $firstVisibleLi = $('.infotabs.responsive li:visible:first');
                                var targetPaneId = $firstVisibleLi.find('a').attr('href');
                                $('.tab-pane').removeClass('active');
                                $('.infotabs li').removeClass('active');
                                $firstVisibleLi.addClass('active');
                                $(targetPaneId).addClass('active');
                            }
                        }

                        self.loadProductThumbnails();

                        try { TurnToCmd('set', { sku: String(data.newSku) }); } catch (e) { }

                        mpSpinner.hide();
                        linkTrack('productDetail');

                        self.handlers.producPageReStructure();
                     
                        // need to reattach affix event handlers
                        /*Remove sticky cart temporary
                        self.handlers.setupAffixElements();
                        self.handlers.setupScrollspy();
            
                        self.refreshStickyCart($(data.infoPartialView).find('.cart-copy'));*/
                    }
                }
               
                window.scrollTo(0, 0);
            },
            error: function () {
                mpSpinner.hide();
                location.href = '/StaticContent/generalerror';
            }
        });
    };

    View.prototype.initializeProductAttributes = function () {
        var width = $(window).width();

        Util.timer('setupproductattributes', function () {
            this.setupProductAttributes(width);
        }.bind(this), 250);
    };

    View.prototype.initializeStickyCart = function () {
        var cartSec = $('.cart-sec-1').clone();
        $($('.add-to-cart-form')[1]).prepend(cartSec);
    };

    View.prototype.refreshStickyCart = function (html) {
        $('.mp-sticky-cart').find('.cart-copy').html(html);
    };

    View.prototype.initializeSpinner = function () {
        var $spinner = $('<div class="mp-spinner-overlay"><div class="mp-spinner"><i class="fa fa-circle-o-notch fa-spin"></i></div></div>');

        mpSpinner = {
            show: function () {
                $("body").append($spinner);
            },
            hide: function () {
                $spinner.remove();
            }
        };
    };

    moduleInstance = new View();
    return moduleInstance;
});

$(document).ready(function () {
    $(document).on("click", ".lihidable a", function (e) {
        //var URL = $(this).attr("href");
        //$(".setUrl").attr("href", URL);
        //$(".setUrl img").attr("src", URL);
        //$(this).find("img").addClass("curr");
        //e.preventDefault();

        var largeImage = $(this).find('.img-thumb').data('largeimg');

        $('.curr').removeClass('curr');

        if (largeImage) {
            $(this).find('img').addClass('curr');

            $(".monowrap .setUrl").attr("href", largeImage);

            $('.monowrap img#mono4').attr({
                src: largeImage
            }).removeClass('hidden');

            $('#ytVideo').hide();

        } else {
            var videoId = $(this).find('.img-thumb').data('video'),
                videoSrc = '//www.youtube.com/embed/' + videoId;
            $('#ytVideo').attr({
                src: videoSrc
            });
            $(this).find('img').addClass('curr');

            $('#ytVideo').show();
            $('img#mono4').attr('src', '').addClass('hidden');
        }

        e.preventDefault();
    });
});
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

    function setupMenuAim() {
        if ($menu.menuAim) {
            // jQuery-menu-aim: Hook up events to be fired on menu row activation.         
            $menu.menuAim({
                activate: activateSubmenu,
                deactivate: deactivateSubmenu
            });
        } else {
            window.setTimeout(setupMenuAim, 500);
        }
    }

    setupMenuAim();
 
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