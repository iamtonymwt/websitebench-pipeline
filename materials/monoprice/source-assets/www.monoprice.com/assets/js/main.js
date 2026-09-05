require.config({
    baseUrl: '/assets/js',
    urlArgs: "bust=" + window.MPI.version,
    paths: {
        'jquery': '/assets/javascripts/jquery.min',
        'modules': '/assets/js/modules',
        'lit-all': '/Scripts/lit-all.min', 
    }
});

require(['jquery', 'modules'], function ($, modules) {
    // Initialize jQuery and modules
    for (var module in modules) {
        module = modules[module];

        if (module.init && $.isFunction(module.init)) {
            module.init();
        }
    }

    // Components are automatically registered as custom elements
}, function (err) {
    var failedId = err.requireModules && err.requireModules[0];
    if (failedId === 'jquery') {
        requirejs.undef(failedId);

        // Set the path to jQuery to local path
        requirejs.config({
            paths: {
                'jquery': 'assets/javascripts/jquery.min.js'
            }
        });

        require(['jquery'], function () { });
    } else {
        // Some other error. Maybe show message to the user.
    }
});