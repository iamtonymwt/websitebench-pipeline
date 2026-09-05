(function (window, jQuery, dataLayerName) {
    var $ = jQuery;
    var document = window.document;
    var MPI = window.MPI = window.MPI || {};
    var initialized = false;
    var initializing = false;
    var slidebar = null;
    var oninit = jQuery.Deferred();

    // PRIVATE

    function render(results) {
        $(".monoMiniContent").each(function () {
            $(this).html(results.miniCart);
       
        });
        $("#myBagCount, .mycart, .cart-value").html(" " + results.itemCount + " items");
        $("mycart, .cart-value").html(results.itemCount);
        $(".my-cart #myBagSubTotal").html(results.subTotal);
        $(".mobile-myBagSubTotal").html(results.subTotal);
        /*$(".checkout__button").html('<i class="glyphicon glyphicon-shopping-cart"></i> ' + results.itemCount);*/
        resizeMonoMini();
    }

    function renderLoading() {
        jQuery('.monoMiniContent').html('<div class="loading-box"><img src="https://images.monoprice.com/assets/images/loading-img.gif" alt="" class="icn-loading" /></div>');
        jQuery('.monoMiniContent').focus();
   
        resizeMonoMini();
    }

    function resizeMonoMini() {
        if ($('#monoMini').hasClass('animated') &&
            $('#monoMini').css('display') === 'block') {
            var contentheight = $(".monoMiniContent").height() + $("#monoMiniBottom").height();
            var miniheight = contentheight < 390 ? contentheight + 30 : 390;
            $('#monoMini').height(miniheight + "px");
        }
    }

    function onHoverIn() {
        if ($("#top-header-item-count").html() < 1 ||
            $('#monoMini').hasClass('animated')) {
            return;
        }

        $('#monoMini').css('display', 'block');

        var contentheight = $(".monoMiniContent").height() + $("#monoMiniBottom").height();
        var miniheight = contentheight < 390 ? contentheight + 33 : 390;

        $('#monoMini').dequeue().stop().animate({ height: miniheight + "px" }, 100, function () {
            $('#monoMini').addClass('animated').dequeue();
            MPI.ee.checkout(1);
        });
    }

    function onHoverOut() {
        $('#monoMini').addClass('animated').animate({ height: "0" }, 100, function () {
            $('#monoMini').css('display', 'none');
            $('#monoMini').removeClass('animated').dequeue();
        });
    }

    // PUBLIC

    function init() {
        if (initializing || initialized) {
            return oninit;
        }

        initializing = true;

        // These buttons implicitly tell us if we are on a page that has a minicart
        // implementation. If they do not exist, then we should not be loading
        // minicart data nor attaching event handlers.
        //if (jQuery('.checkout__button').length < 1 &&
        //    jQuery('ul#carttab li#cart-tab').length < 1) {
        //  setTimeout(function() {
        //    initializing = false;
        //    initialized = true;
        //    oninit.resolve();
        //  }, 0);
        //  return oninit;
        //}

        if (!slidebar && typeof jQuery.slidebars === 'function') {
            slidebar = new jQuery.slidebars();
        }

        // Close Slidebar via Link
        jQuery('.sb-close2').on('click', function () {
            e.preventDefault();
            hide();
        });

        jQuery('.checkout__button').on('click', function (e) {
            /*e.preventDefault();*/
            MPI.ee.checkout(1);
            show();
        });

        jQuery('.checkout__cancel').on('click', function (e) {
            e.preventDefault();
            hide();
        });

        jQuery("ul#carttab li#cart-tab")
          .hover(onHoverIn, onHoverOut);

        // Load and then make sure we return nothing to the call to keep a
        // consistent init return type
        load()
          .done(function () {
              initializing = false;
              initialized = true;
              oninit.resolve();
          })
          .fail(function (err) {
              var _oninit = oninit;
              oninit = MPI.minicart.oninit = jQuery.Deferred();
              initialized = false;
              initializing = false;
              _oninit && _oninit.reject(err);
          });

        return oninit;
    }

    function load() {
        renderLoading();

        return jQuery.getJSON('/cart/minicart')
          .then(function (results) {
              MPI.ee.cacheCartItems(results.items);
              render(results);

              var currentLocation = window.location;
              if (currentLocation.href.includes('cart') == true) {
                  callListrak();
              }
              return results;
          });
    }

    function show() {
        if (initialized) {
            if (jQuery(window).width() <= 1215) {
                jQuery('.mobile-mycart-dropdown').addClass('open');
            } else {
                jQuery('.mycart-dropdown').addClass('active');
            }
            jQuery(window).scrollTop(0);
           // jQuery('.lw_monoMiniItemText a').focus();
            setTimeout(function () {
                jQuery('.mycart-dropdown').removeClass('active');
                jQuery('.mobile-mycart-dropdown').removeClass('open');
            }, 3000);
        }
    }
    jQuery('.my-cart').click(function () {

     //   jQuery('.lw_monoMiniItemText a').focus();
        jQuery('.mp-emptycart a').focus();
    });
    function hide() {
        var href = window.location.href.replace(/\#+(.*)$/gm, '');

        if (initialized) {
            jQuery('.checkout').removeClass('checkout--active');
            $('.cart-tab').not('.view-mobile').removeClass('open');
            // close all targeted flyouts
            window.location.href = href + '#';
        }
    }

    function add(productId, quantity) {
        quantity = parseInt(quantity, 10);

        if (!productId) {
            return jQuery.Deferred()
              .reject(new Error('Missing product id'));
        }

        if (quantity < 1) {
            return jQuery.Deferred()
              .reject(new Error('Quantity must be a positive integer'));
        }

        renderLoading();

        var oldItem = MPI.ee.findItemByField('cart', 'id', productId);
        var oldQty = 0;
        if (oldItem !== undefined) {
            oldQty = oldItem.quantity;
        }

        return jQuery.post('/Cart', {
            p_id: productId || '',
            qty: quantity || ''
        })
          .then(function () {
              return jQuery.getJSON('/cart/minicart');
          })
          .then(function (results) {
              MPI.ee.cacheCartItems(results.items);

              var updatedItem = MPI.ee.findItemByField('cart', 'id', productId);
              var updatedQty = 0;
              if (updatedItem !== undefined) {
                  updatedQty = updatedItem.quantity;
              }
              MPI.ee.addToCart([{ id: productId, quantity: updatedQty - oldQty }]);
              render(results);

              var result = jQuery.Deferred();

              setTimeout(function () {
                  show();
                  result.resolve();
              }, 0);
              if (updatedQty > 0) {
                  callListrak();
              }
              return result;
          });
    }

    function remove(cartItemId) {
        var cartItem;

        if (!cartItemId) {
            return jQuery.Deferred().resolve();
        }

        cartItem = MPI.ee.findCartItem(cartItemId);

        renderLoading();

        return jQuery.post('/cart/minicart', 'ca_idx=' + cartItemId)
          .then(function (results) {
              MPI.ee.cacheCartItems(results.items);
              render(results);
              MPI.ee.removeFromCart(cartItem);

              callListrak();
              ClearCartListrak();
              return results;
          });
    }

    function ClearCartListrak() {
        (function () {
            if (typeof _ltk == 'object') { ltkCode(); } else { (function (d) { if (document.addEventListener) document.addEventListener('ltkAsyncListener', d); else { e = document.documentElement; e.ltkAsyncProperty = 0; e.attachEvent('onpropertychange', function (e) { if (e.propertyName == 'ltkAsyncProperty') { d(); } }); } })(function () { ltkCode(); }); } function ltkCode() {
                _ltk_util.ready(function () {
                    /********** Begin Custom Code **********/
                    if (digitalData.cart.length == 0) {
                        console.log('listrak clear cart');
                        _ltk.SCA.ClearCart();
                    }
                    /********** End Custom Code ************/
                })
            }
        })();
    }

    // Expose global functions for pre-existing behaviors
    window.updateitemcart = function updateitemcart(id) {
        id ? remove(id) : load();
        return false;
    };

    // This only applies to B2C since the B2B function does not exist and the
    // form is posted as a standard html form post
    window.func_addtocart = function func_addtocart(form, callback) {
        if (jQuery('#monoMini').length < 1) {
            form = form || this || {};
            add((form.p_id || {}).value, (form.qty || {}).value).done(callback);
            return false;
        }
    };

    MPI.minicart = {
        init: init,
        load: load,
        hide: hide,
        add: add,
        remove: remove,
        show: show,
        oninit: oninit,
    };

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

})(window, jQuery);
