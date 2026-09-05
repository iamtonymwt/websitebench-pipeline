$(function (window) {
    var shopBtn = '#shopBtn';
    var shopDropDown = '.shop-dropdown';
    var featBtn = '#featBtn';
    var featDropDown = '.brands-nav';
    var mpBusinessBtn = '#monoBtn';
    var mpBusinessDropDown = '.mp-business-nav';
    var acctBtn = '#acctBtn';
    var acctDropDown = '.my-acct-dropdown';
    var quickBtn = '#quickOrder';
    var quickDropDown = '.quick-order-dropdown';
    var cartBtn = '#myCart';
    var cartDropDown = '.mycart-dropdown';
    var mobileCartDropDown = '.mobile-mycart-dropdown';
    var mobileNav = '.mp-mobile-nav';
    var mobileNavBtn = '#mobileNavBtn';
    var mobileNavOverlayBtn = '#mobileNavOverlay';
    var mobileNavCloseBtn = '#mobileNavClose';
    var mobileCartOverlayBtn = '#mobileCartOverlay';
    var mobileCartCloseBtn = '#mobileCartClose';
    var mobileDropDown = '.mp-mobile-nav .shop-dropdown';
    var mainCategoryBtn = '.mobile-category';
    var subCategory = '.megamenu-sub';
    var subCategoryBtn = '.mobile-subcategory';
    var childCategory = '.child-list';
    var mpSearch = '.mp-search';
    var mobileSearchBtn = '.mobile-search-icon';
    var mobileCartBtn = '.mp-mobile-cart';
    var timeout;
    var active = 'active';
    var open = '.open';
    var openClass = 'open';
    var back = '.back';
    var mobileMenuOpenClass = 'mobile-menu-open';
    var mobileSearchOpenClass = 'mobile-search-open';
    var mobileCartOpenClass = 'mobile-cart-open';
    var mobileNavPanel = '.mp-mobile-nav .shop-nav';
    var mobileHeaderWrap = 'header .header-container';

    function setMobileNavState(isOpen) {
        $(mobileNavPanel).toggleClass(active, isOpen);
        $(mobileHeaderWrap).toggleClass(mobileMenuOpenClass, isOpen);
        $('body').toggleClass(mobileMenuOpenClass, isOpen);
        if (!isOpen) {
            $(mobileNav).find(open).removeClass(openClass);
            $(mobileCartDropDown).removeClass(openClass);
            $(back).hide();
        }
    }

    function closeMobileNav() {
        setMobileNavState(false);
    }

    function setMobileSearchState(isOpen) {
        $(mpSearch).toggleClass(openClass, isOpen);
        $(mobileHeaderWrap).toggleClass(mobileSearchOpenClass, isOpen);
        $('body').toggleClass(mobileSearchOpenClass, isOpen);
    }

    function closeMobileSearch() {
        setMobileSearchState(false);
    }

    function setMobileCartState(isOpen) {
        $(mobileCartDropDown).toggleClass(openClass, isOpen);
        $(mobileHeaderWrap).toggleClass(mobileCartOpenClass, isOpen);
        $('body').toggleClass(mobileCartOpenClass, isOpen);
    }

    function closeMobileCart() {
        setMobileCartState(false);
    }

    function isMobileCartOpen() {
        return $(mobileCartDropDown).hasClass(openClass);
    }

    function isMobileNavOpen() {
        return $(mobileNavPanel).hasClass(active);
    }

    // Toggle Shop Navigation //
    $(shopBtn).click(function () {
        $("#featBtn").attr("tabindex", "-1");
        $(shopDropDown).toggleClass(active);
    });

    $(document).click(function (e) {
        if ($(e.target).closest(shopBtn).length === 0) {
            $(shopDropDown).removeClass(active);
        }
    });

    // Toggle Feat Products //
    $(featBtn).click(function () {
        $(featDropDown).toggleClass(active)
    });

    $(document).click(function (e) {
        if ($(e.target).closest(featBtn).length === 0) {
            $(featDropDown).removeClass(active);
        }
    });

    // Toggle Monoprice Business //
    $(mpBusinessBtn).click(function () {
        $(mpBusinessDropDown).toggleClass(active)
    });

    $(document).click(function (e) {
        if ($(e.target).closest(mpBusinessBtn).length === 0) {
            $(mpBusinessDropDown).removeClass(active);
        }
    });

    // Toggle My Account //
    $(acctBtn).click(function () {
        $(acctDropDown).toggleClass(active);
    });

    $(document).click(function (e) {
        if ($(e.target).closest(acctBtn).length === 0) {
            $(acctDropDown).removeClass(active);
        }
    });
    // Toggle Quick Order //
    $(quickBtn).click(function () {
        $('.user-links .myacct-nav').find('.active').removeClass('active');
        $('.user-links .my-cart').find('.active').removeClass('active');
        $(quickDropDown).toggleClass(active)
        $(quickDropDown).find('#quickOrderSKU').focus();
    });

    $('.quick-order').mouseleave(function () {
        timeout = setTimeout(function () {
            $(quickDropDown).removeClass(active, 1000);
        }, 1000);
    });
    // Toggle Quick Cart //
    $(cartBtn).click(function () {
        $('.user-links .quick-order').find('.active').removeClass('active');
        $(cartDropDown).toggleClass(active);
    });

    $(cartDropDown).mouseleave(function () {
        timeout = setTimeout(function () {
            $(cartDropDown).removeClass(active, 500);
        }, 500);
    });

    // Toggle Mobile Nav //
    $(mobileNavBtn).on('click', function (e) {
        e.preventDefault();
        setMobileNavState(!$(mobileNavPanel).hasClass(active));
        if ($(cartDropDown).hasClass(openClass)) {
            $(cartDropDown).removeClass(openClass)
        };
        closeMobileSearch();
        if ($(mobileCartDropDown).hasClass(openClass)) {
            closeMobileCart();
        }
    });

    $(document).on('click', mobileNavCloseBtn + ',' + mobileNavOverlayBtn, function (e) {
        e.preventDefault();
        closeMobileNav();
    });

    $(document).on('click', function (e) {
        if (!isMobileNavOpen()) {
            return;
        }

        if ($(e.target).closest(mobileNavPanel).length > 0) {
            return;
        }

        if ($(e.target).closest(mobileNavBtn).length > 0) {
            return;
        }

        closeMobileNav();
    });

    $(mainCategoryBtn).on('click', function (e) {
        e.preventDefault();
        $(back).show();
        $(this).next(subCategory).toggleClass(openClass);
    });

    $(subCategoryBtn).on('click', function (e) {
        e.preventDefault();
        $(this).next(childCategory).toggleClass(openClass);
    });

    $(back).on('click', function () {
        $(open).last().removeClass(openClass);
        if ($(subCategory).hasClass(openClass)) {
            $(this).show()
        } else {
            $(this).hide()
        }
    });

    // Toggle Mobile Search //
    $(mobileSearchBtn).on('click', function () {
        if ($(mobileNavPanel).hasClass(active)) {
            closeMobileNav();
        }
        closeMobileCart();
        setMobileSearchState(!$(mpSearch).hasClass(openClass));
        $(mpSearch).find('.mp-input-field').focus();           
    });
        
    $(document).click(function (e) {
        if ($(e.target).closest(mobileSearchBtn).length === 0 && $(e.target).closest(mpSearch).length === 0) {
            closeMobileSearch();
        }
    });

    // Toggle Mobile Cart //
    $(mobileCartBtn).on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if ($(mobileNavPanel).hasClass(active)) {
            closeMobileNav();
        }
        closeMobileSearch();
        setMobileCartState(!isMobileCartOpen());
    });

    $(document).on('click', mobileCartCloseBtn + ',' + mobileCartOverlayBtn, function (e) {
        e.preventDefault();
        closeMobileCart();
    });

    $(document).click(function (e) {
        if (!isMobileCartOpen()) {
            return;
        }

        if ($(e.target).closest(mobileCartBtn).length > 0 || $(e.target).closest(mobileCartDropDown).length > 0) {
            return;
        }

        closeMobileCart();
    });
});
