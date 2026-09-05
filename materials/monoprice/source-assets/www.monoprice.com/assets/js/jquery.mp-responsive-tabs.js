(function ( $ ) {
	'use strict';

	var currentPosition;

	$.fn.responsiveTabs = function ( collapseDisplayed ) {

		currentPosition = 'tabs';

		var tabGroups = $(this);
		var hidden    = '';
		var visible   = '';
		var activeTab = '';

		if ( collapseDisplayed === undefined ) {
			collapseDisplayed = [ 'xs', 'sm' ];
		}

		$.each( collapseDisplayed, function () {
			hidden  += ' hidden-' + this;
			visible += ' visible-' + this;
		} );

		$.each( tabGroups, function ( index ) {
			var collapseDiv;
			var $tabGroup = $( this );
			var tabs      = $tabGroup.find( 'li a' );

			if ( $tabGroup.attr( 'id' ) === undefined ) {
				$tabGroup.attr( 'id', 'tabs-' + index );
			}

			collapseDiv = $( '<div></div>', {
				'class' : 'cart-sec-3 panel-group responsive' + visible,
				'id'    : 'collapse-' + $tabGroup.attr( 'id' )
			} );

			$.each( tabs, function () {
				var $this          = $( this );
				var oldLinkClass   = $this.attr( 'class' ) === undefined ? '' : $this.attr( 'class' );
				var newLinkClass   = 'accordion-toggle collapsed';
				var oldParentClass = $this.parent().attr( 'class' ) === undefined ? '' : $this.parent().attr( 'class' );
				var newParentClass = 'panel panel-default';
				var newHash        = $this.get( 0 ).hash.replace( '#', 'collapse-' );

				if ( oldLinkClass.length > 0 ) {
					newLinkClass += ' ' + oldLinkClass;
				}

				if ( oldParentClass.length > 0 ) {
					oldParentClass = oldParentClass.replace( /\bactive\b/g, '' );
					newParentClass += ' ' + oldParentClass;
					newParentClass = newParentClass.replace( /\s{2,}/g, ' ' );
					newParentClass = newParentClass.replace( /^\s+|\s+$/g, '' );
				}

				if ( $this.parent().hasClass( 'active' ) ) {
					activeTab = '#' + newHash;
				}

				collapseDiv.append(
					$( '<div>' ).attr( 'class', newParentClass ).html(
						$( '<div>' ).attr( 'class', 'panel-heading' ).html(
							$( '<h4>' ).attr( 'class', 'panel-title' ).html(
								$( '<a>', {
									'class'       : newLinkClass,
									'data-toggle' : 'collapse',
									'data-parent' : '#collapse-' + $tabGroup.attr( 'id' ),
									'href'        : '#' + newHash,
									'html'        : $this.html()
								} )
							)
						)
					).append(
						$( '<div>', {
							'id'    : newHash,
							'class' : 'panel-collapse collapse'
						} )
					)
				);
			} );

			$tabGroup.after( collapseDiv );
			$tabGroup.addClass( hidden );
			$( '.tab-content.responsive' ).addClass( hidden );

			if ( activeTab ) {
				$( activeTab ).collapse( 'show' );
			}
		} );

		checkResize();
		bindTabToCollapse();
	};

	var checkResize = function () {

		if ( $( '.panel-group.responsive' ).is( ':visible' ) === true && currentPosition === 'tabs' ) {
			tabToPanel();
			currentPosition = 'panel';
		} else if ( $( '.panel-group.responsive' ).is( ':visible' ) === false && currentPosition === 'panel' ) {
			panelToTab();
			currentPosition = 'tabs';
		}

	};

	var tabToPanel = function () {

		var tabGroups = $( '.infotabs.responsive' );

		$.each( tabGroups, function ( index, tabGroup ) {

			// Find the tab
			var tabContents = $( '.tab-content' ).find( '.tab-pane' );

			$.each( tabContents, function ( index, tabContent ) {
				// Find the id to move the element to
				var destinationId = $( tabContent ).attr( 'id' ).replace ( /^/, '#collapse-' );

				// Convert tab to panel and move to destination
				$( tabContent )
					.removeClass( 'tab-pane' )
					.addClass( 'panel-body fw-previous-tab-pane' )
					.appendTo( $( destinationId ) );

			} );

		} );

	};

	var panelToTab = function () {

		var panelGroups = $( '.panel-group.responsive' );

		$.each( panelGroups, function ( index, panelGroup ) {

			var destinationId = $( panelGroup ).attr( 'id' ).replace( 'collapse-', '#' );
			var destination   = $( '.tab-content' )[ 0 ];

			// Find the panel contents
			var panelContents = $( panelGroup ).find( '.panel-body.fw-previous-tab-pane' );
			var activeTab = $( panelContents ).eq(0).addClass('active');

			// Convert to tab and move to destination
			panelContents
				.removeClass( 'panel-body fw-previous-tab-pane' )
				.addClass( 'tab-pane' )
				.appendTo( $( destination ) );

		} );

	};

	var bindTabToCollapse = function () {

		var tabs     = $( '.infotabs.responsive' ).find( 'li a' );
		var collapse = $( '.panel-group.responsive' ).find( '.panel-collapse' );

		// Toggle the panels when the associated tab is toggled
		tabs.on( 'shown.bs.tab', function ( e ) {

			if (currentPosition === 'tabs') {
				var $current  = $( e.currentTarget.hash.replace( /#/, '#collapse-' ) );
				$current.collapse( 'show' );

				if ( e.relatedTarget ) {
					var $previous = $( e.relatedTarget.hash.replace( /#/, '#collapse-' ) );
					$previous.collapse( 'hide' );
				}
			}

		} );

		// Toggle the tab when the associated panel is toggled
		collapse.on( 'shown.bs.collapse', function ( e ) {

			if (currentPosition === 'panel') {
				// Activate current tabs
				var current = $( e.target ).context.id.replace( /collapse-/g, '#' );
				$( 'a[href="' + current + '"]' ).tab( 'show' );

				// Update the content with active
				var panelGroup = $( e.currentTarget ).closest( '.panel-group.responsive' );
				$( panelGroup ).find( '.panel-body' ).removeClass( 'active' );
				$( e.currentTarget ).find( '.panel-body' ).addClass( 'active' );
			}

		} );
	};

	$(window).resize( function () {
		checkResize();
	});

	$(document).on('click', '.infotabs li > a, .accordion-toggle', function (e) {
		e.preventDefault();
		var $target = $(e.target),
			delay = 333;

		var goToTab = function ($destination) {
			var cartBtnsHeight = $('.cart-btns.affix').height();
			var cartBtnsMockHeight = 113;
			var offset = ($destination.offset().top - cartBtnsHeight);

			if ($destination.is($(e.target))) {
				offset = offset - cartBtnsMockHeight;
			} else if ($('.info-row').hasClass('affix')) {
				offset = offset - cartBtnsMockHeight + 45;
			} else {
				offset = $destination.offset().top - cartBtnsMockHeight - 65;
			}

		    $('html, body').animate({
		        scrollTop: offset
		    });
		};

		if ($target.is('.accordion-toggle')) {
			if ($target.closest('.panel').find('.panel-collapse').is(':visible')) {
				goToTab($(e.target));
			}
		} else {
			$(this).tab('show');
			goToTab($('.tab-content'));
		}
	});

}( jQuery ));
