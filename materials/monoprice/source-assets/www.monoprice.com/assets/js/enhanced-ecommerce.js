(function (window, jQuery, dataLayerName, googleDataLayerName) {
  var $ = jQuery;
  var document = window.document;
  var location = window.location;
  var MPI = window.MPI = window.MPI || {};

  var DEBUG = window.DEBUG != null ? Boolean(window.DEBUG) : (
    location.hostname === '127.0.0.1' ||
    location.hostname === 'localhost' ||
    /^dev(\d*)\.monoprice\.com$/.test(location.hostname)
  );

  var CART_CACHE_KEY = 'cart';
    var CART_ITEM_FIELDS = [
        'uid',
        'id',
        'productID',
        'name',
        'brand',
        'category',
        'merchandising',
        'productSubcategory2',
        'variant',
        'price',
        'quantity',
        'coupon',
        'productGroupID',
        'sale',
        'adjustment',
        'freeShippingItemLimit',
        'productImageUrl',
        'productPageUrl',
        'discountedPriceTotal'
    ];

  var PURCHASE_CACHE_KEY = 'purchase';
    var PURCHASE_ITEM_FIELDS = [
        'uid',
        'id',
        'affiliation',
        'total',
        'tax',
        'shipping',
        'coupon',
        'paymentMethod',
        'shippingMethod',
        'giftCard',
        'subTotal',
        'totalSavings',
        'adjustment',
        'products',
        'firstName',
        'lastName',
        'email'
    ];

  dataLayerName = dataLayerName || 'digitalData';
  window[dataLayerName] = window[dataLayerName] || [];

  googleDataLayerName = googleDataLayerName || 'dataLayer';
  window[googleDataLayerName] = window[googleDataLayerName] || [];

  // PRIVATE

  function log(level) {
    if (typeof console === 'object' &&
        console != null &&
        typeof console[level] === 'function') {
      console[level].apply(console, Array.prototype.slice.call(arguments, 1))
    }
  }

  log.debug = function() {
    if (DEBUG) {
      log.apply(this, ['log', '[GA EE]'].concat(Array.prototype.slice.call(arguments)));
    }
  }

  log.info = function() {
    log.apply(this, ['info', '[GA EE]'].concat(Array.prototype.slice.call(arguments)));
  };

  log.warn = function() {
    log.apply(this, ['warn', '[GA EE]'].concat(Array.prototype.slice.call(arguments)));
  };

  log.error = function() {
    log.apply(this, ['error', '[GA EE]'].concat(Array.prototype.slice.call(arguments)));
  };

  function identity(value) {
    return value;
  }

  function parseInteger(value, base) {
    base = typeof base === 'number' ? base : 10;
    value = value === 0 ? '0' : value;

    if (value == null ||
        isNaN(value) ||
        value === Infinity ||
        value === -Infinity) {
      value = '';
    }

    value = String(value || '');
    value = value.match(/^(\d+)$/g) || [];
    value = parseInt(value[0], base);
    return isNaN(value) ? undefined : value;
  }

  function parseBoolean(value) {
    if (typeof value === 'boolean') {
      return value;
    }

    if (value === 1) {
      return true;
    }

    if (typeof value !== 'string') {
      return false;
    }

    value = value
      .toLowerCase()
      .replace(/^\s+|\s+$/g, '');

    return (
      value === 'true' ||
      value === 't' ||
      value === 'yes' ||
      value === 'y' ||
      value === '1'
    );
  }

  function parseCheckoutOption(value, defaultValue) {
    if (typeof value === 'string') {
      return value;
    }

    if (value == null || isNaN(value) || value === Infinity || value === Infinity) {
      return defaultValue;
    }

    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }

    return defaultValue;
  }

  function push(obj) {
    var msg, result;

    if (!window[googleDataLayerName] || typeof window[googleDataLayerName].push !== 'function') {
      msg = 'Environment has changed and now unable to push GTM event';
      log.error(msg, obj);
      return jQuery.Deferred().reject(new Error(msg));
    }

    if (!jQuery.isPlainObject(obj)) {
      msg = 'Cannot push value that is not a plain object';
      log.error(msg, obj);
      return jQuery.Deferred().reject(new Error(msg));
    }

    result = jQuery.Deferred();

    obj.eventCallback = function() {
      result.resolve();
    };

    window[googleDataLayerName].push(obj);
    log.debug('Event pushed', obj);

    return result;
  }

  function mapSingleOrMany(obj, callback) {
    obj = jQuery.isArray(obj) ? obj : [obj];

    return jQuery.map(obj, function (item) {
      if (item == null || typeof callback !== 'function') {
        return item;
      }

      return callback(item);
    });
  }

  function setCacheArray(key, array, mapper) {
    var dataLayer, cache;

    if (!window[dataLayerName]) {
      log.error('Environment has changed and cannot cache data', key, array);
      return;
    }

    dataLayer = window[dataLayerName];
    cache = dataLayer[key];

    if (!cache) {
      dataLayer[key] = mapSingleOrMany(array, mapper);
      array = dataLayer[key].slice();
    } else {
      Array.isArray(cache) || log.warn('Overriding non-array cache key', key, cache);
      array = mapSingleOrMany(array, mapper);
      cache.splice.apply(cache, [0, cache.length].concat(array));
    }

    log.debug('Updated cache', key, array);

    return array;
  }

  function getCacheArray(key, mapper) {
    var cache = key && window[dataLayerName] && window[dataLayerName][key];
    return jQuery.isArray(cache) ? mapSingleOrMany(cache, mapper) : [];
  }

  function findInCache(key, callback) {
    if (!key || typeof callback !== 'function') {
      return;
    }

    var key;
    var cache = window[dataLayerName][key] || [];

    if (jQuery.isArray(cache)) {
      for (key = 0; key < cache.length; key++) {
        if (callback(cache[key])) {
          return cache[key];
        }
      }
    }
    else {
      for (key in cache) {
        if (callback(cache[key])) {
          return cache[key];
        }
      }
    }
  }

  function createObject(item, fields, ignoreUID) {
    return (createObjects(item, fields, ignoreUID) || [])[0];
  }

  function createObjects(items, fields, ignoreUID) {
    var cartItem;
    var empty = true;

    return mapSingleOrMany(items, function(item) {
      cartItem = {};
      empty = true;

      jQuery.each(fields, function(index, field) {
        if (item.hasOwnProperty(field) && (field !== 'uid' || !ignoreUID)) {
          empty = false;
          cartItem[field] = item[field];
        }
      });

      if (!empty) {
        return cartItem;
      }
    });
  }

  function createPurchase(purchase, ignoreUID) {
    var products;

    purchase = createObject(purchase, PURCHASE_ITEM_FIELDS, ignoreUID);

    if (purchase && jQuery.isArray(purchase.products)) {
      products = createCartItems(purchase.products, ignoreUID);
    }

    if (purchase && jQuery.isArray(products)) {
      purchase.products = products;
    }

    return purchase;
  }

  function createCartItem(item, ignoreUID) {
    return createObject(item, CART_ITEM_FIELDS, ignoreUID);
  }

  function createCartItems(items, ignoreUID) {
    return mapSingleOrMany(items, function(item) {
      return createCartItem(item, ignoreUID);
    });
  }

  function getCartItems(ignoreUID) {
    return getCacheArray(CART_CACHE_KEY, function(item) {
      return createCartItem(item, ignoreUID);
    });
  }


  // PUBLIC

  function findItemByField(cacheKey, field, value) {
    if (cacheKey && field && value != null) {
      return findInCache(cacheKey, function (item) {
        return (item || {})[field] === value;
      });
    }
  }

  function addToCart(items) {
    var cartItems = [];
    for (var i = 0; i < items.length; i++) {
      var productId = items[i].id;
      var quantity = items[i].quantity;

      var item = findItemByField(CART_CACHE_KEY, 'id', String(productId || ''));
      var cartItem = createCartItem(item, true);
      var parsedQuantity = parseInteger(quantity);

        addCartItemToGA(item);

      if (!parsedQuantity && parsedQuantity !== 0) {
        parsedQuantity = null;
      }

      if (!item) {
        log.warn('Cart item not found for product id', productId);
        return jQuery.Deferred().resolve();
      }

      if (!cartItem) {
        log.warn('Cart item was not created', item);
        return jQuery.Deferred().resolve();
      }

      parsedQuantity == null && log.warn('Quantity is null', quantity);
      cartItem.quantity = parsedQuantity;

      if (item.quantity == parsedQuantity) {
          cartItems.push(cartItem);
      }
    }

    if (cartItems.length > 0) {
        var dataLayer = window[dataLayerName];
        dataLayer.addToCart = cartItems;

        var siteType = dataLayer.page.pageInfo.siteType;
        if (siteType == "B2C") {
            var addPath = window.location.pathname;
        }
        else {
            var addPath = document.referrer.substring(document.referrer.indexOf("/", 8));
        }

        if (addPath.toLowerCase().indexOf("/category") == 0) {
            dataLayer.addToCart.event = "event36";
        }
        else if (addPath.toLowerCase().indexOf("/search") == 0) {
            dataLayer.addToCart.event = "event28";
        }
        else {
            dataLayer.addToCart.event = 'event37';
        }
        linkTrack('cartAdd');
    }
    }

    function addCartItemToGA(item) {
        // Measure adding a product to a shopping cart by using an 'add' actionFieldObject
        // and a list of productFieldObjects.
        dataLayer.push({ ecommerce: null });  // Clear the previous ecommerce object.
        dataLayer.push({
            'event': 'addToCart',
            'ecommerce': {
                'currencyCode': 'US',
                'add': {                                // 'add' actionFieldObject measures.
                    'products': [{                        //  adding a product to a shopping cart.
                        'name': item.name,
                        'id': item.id,
                        'price': item.price,
                        'brand': item.brand,
                        'category': item.category,
                        'variant': item.variant,
                        'quantity': item.quantity
                    }]
                }
            }
        });
    }

  function cacheCartItems(items) {
    return setCacheArray(CART_CACHE_KEY, items, createCartItem);
  }

  function checkout(step, option, items) {
    var parsedStep = parseInteger(step);
    var parsedOption = parseCheckoutOption(option);

    if (jQuery.isArray(option)) {
      items = option;
      option = undefined;
    }

    if (!parsedStep || parsedStep < 1) {
      var msg = 'Expected checkout step to be an integer > 0';
      log.error(msg, step);
      return jQuery.Deferred().reject(new Error(msg));
    }

    var cartItems = jQuery.isArray(items) ?
      createCartItems(items, true) :
      getCartItems(true);

    // Do not log the first checkout step when the cart is empty
    if (parsedStep === 1 && cartItems.length < 1) {
      return jQuery.Deferred().resolve();
    }

    var dataLayer = window[dataLayerName];
    dataLayer.checkout = {
      actionField: {
        step: parsedStep,
        option: parsedOption || null
      },
      products: cartItems
    };
  }

  function checkoutOption(step, option) {
    var parsedStep = parseInteger(step);
    var parsedOption = parseCheckoutOption(option);

    if (!parsedStep || parsedStep < 1) {
      var msg = 'Expected checkout step to be an integer > 0';
      log.error(msg);
      return jQuery.Deferred().reject(new Error(msg));
    }

    if (!parsedOption) {
      log.warn('Checkout option called without an option');
      return jQuery.Deferred().resolve();
    }

    return push({
      event: 'checkoutOption',
      ecommerce: {
        checkout_option: {
          actionField: {
            step: parsedStep,
            option: parsedOption
          }
        }
      }
    });
  }

  function checkoutOptionListen(options) {
    options = options || {};

    var handleEvent;
    var step = parseInteger(options.step);
    var event = typeof options.event !== 'string' ? undefined : (options.event || undefined);
    var eventKey = event && event + '.mpi.ee.checkoutOptionListen';
    var selector = options.selector;
    var input = options.input;
    var value = options.value;
    var retrigger = parseBoolean(
      options.retrigger === undefined ? true : options.retrigger
    );
    var transform = typeof options.transform === 'function' ?
      options.transform :
      identity;

    if (!step || step < 1) {
      return log.warn(
        'Checkout option listener expected step to be a positive integer',
        options.step
      );
    }

    if (!event) {
      return log.warn(
        'Checkout option listener expected an event name',
        options.event
      );
    }

    if (!selector) {
      return log.warn(
        'Checkout option listener expected a selector',
        options.selector
      );
    }

    handleEvent = function(e) {
      var inputElement;
      var option = value;

      if (input) {
        inputElement = jQuery(input, selector);
        option = inputElement.data('ga-ee-checkout-option');

        option = (option == null || option === '') ?
          transform(inputElement.val()) :
          transform(option);
      }

      if (!retrigger) {
        MPI.ee.checkoutOption(step, option);
        return;
      }

      e.preventDefault();
      e.stopImmediatePropagation();
      jQuery(e.target).unbind(eventKey);

      MPI.ee
        .checkoutOption(step, option)
        .always(function() {
          jQuery(e.target)
            .trigger(e.type)
            .bind(eventKey, handleEvent);
        });

      return false;
    };

    jQuery(document).ready(function() {
      jQuery(selector)
        .bind(eventKey, handleEvent);

      jQuery(selector).length < 1 &&
        log.warn('Checkout option listener not listening', selector);
    });
  }

  function purchase(purchase) {
    purchase = createPurchase(purchase);

    if (!purchase) {
      log.warn('Invalid purchase provided');
      return jQuery.Deferred().resolve();
    }

    if (!purchase.id) {
      log.warn('Puchase event missing transaction id', purchase);
      return jQuery.Deferred().resolve();
    }

    if (!purchase.products || purchase.products.length < 1) {
      log.warn('Purchase did not have any products', purchase)
      return jQuery.Deferred().resolve();
    }

    var dataLayer = window[dataLayerName];

    dataLayer.transaction = {
        transactionID: purchase.id,
        shippingMethod: purchase.shippingMethod,
        paymentMethod: purchase.paymentMethod,
        promoCode: purchase.coupon,
        giftCard: purchase.giftCard,
        orderSubTotal: purchase.subTotal,
        orderShippingCharges: purchase.shipping,
        orderTax: purchase.tax,
        totalSavings: purchase.adjustment,
        cartTotal: purchase.total,
        purchaseID: purchase.id,
        item: purchase.products,
        affiliation: purchase.affiliation,
        firstName: purchase.firstName,
        lastName: purchase.lastName,
        email: purchase.email
    };

    push({
        event: 'purchase',
        ecommerce: {
            purchase: {
                actionField: {
                    id: purchase.id,
                    affiliation: purchase.affiliation,
                    revenue: purchase.total,
                    tax: purchase.tax,
                    shipping: purchase.shipping,
                    coupon: purchase.coupon
                },
                products: purchase.products
            }
        }
    });

    var transactionItems = [];
    for (var i = 0; i < purchase.products.length; i++) {
        transactionItems.push({
            'sku': purchase.products[i].productID,
            'name': purchase.products[i].name,
            'category': purchase.products[i].category,
            'price': purchase.products[i].price,
            'quantity': purchase.products[i].quantity
        });
    }

    push({
        'transactionId': purchase.id,
        'transactionAffiliation': purchase.affiliation,
        'transactionTotal': purchase.total,
        'transactionTax': purchase.tax,
        'transactionShipping': purchase.shipping,
        'transactionProducts': transactionItems
    });
  }

  function findCartItem(uid) {
    uid = String(uid || uid === 0 ? uid : '');
    return findItemByField(CART_CACHE_KEY, 'uid', uid);
  }

  function removeFromCart(item) {
    var cartItem;
    var uid = item;

    if ((typeof item === 'string' || typeof item === 'number') &&
        (item || item === 0)) {
      item = findCartItem(item);

      if (!item) {
        log.warn('Cart item not found for uid', uid);
        return jQuery.Deferred().resolve();
      }
    }

    var cartItem = createObject(item, CART_ITEM_FIELDS, true);

    if (!cartItem) {
      log.warn('Cart item was not created', item);
      return jQuery.Deferred().resolve();
    }
    
    var dataLayer = window[dataLayerName];
    var isRemoved = false;
    if (findCartItem(item.uid) == undefined) {
        isRemoved = true;
    }
    else if (dataLayer.cart !== undefined) {
        for (var i = 0; i < dataLayer.cart.length; i++)
        {
            if (dataLayer.cart[i].productID == item.productID && dataLayer.cart[i].quantity == item.quantity) {
                isRemoved = true;
                break;
            }
        }
    }
    if (isRemoved) {
        dataLayer.removeFromCart = cartItem;
        linkTrack('cartRemove');
        removeCartItemFromGA(cartItem)
        }
    }

    function removeCartItemFromGA(item) {
        // Measure the removal of a product from a shopping cart.
        dataLayer.push({ ecommerce: null });  // Clear the previous ecommerce object.
        dataLayer.push({
            'event': 'removeFromCart',
            'ecommerce': {
                'remove': {                               // 'remove' actionFieldObject measures.
                    'products': [{                          //  removing a product to a shopping cart.
                        'name': item.name,
                        'id': item.id,
                        'price': item.price,
                        'brand': item.brand,
                        'category': item.category,
                        'variant': item.variant,
                        'quantity': item.quantity
                    }]
                }
            }
        });
    }

  MPI.ee = {
    addToCart: addToCart,
    cacheCartItems: cacheCartItems,
    checkout: checkout,
    checkoutOption: checkoutOption,
    checkoutOptionListen: checkoutOptionListen,
    findCartItem: findCartItem,
    removeFromCart: removeFromCart,
    purchase: purchase,
    findItemByField: findItemByField
  };
})(window, jQuery);
