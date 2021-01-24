$.oauthpopup = function(options) {
  options.windowName = 'ConnectWithOAuth'; // should not include space for IE
  options.windowOptions = 'location=0,status=0,width=800,height=400';
  options.callback = options.callback || function() {
    window.location.reload();
  };

  var that = this;
  that._oauthWindow = window.open(
    options.path, options.windowName, options.windowOptions);
  that._oauthInterval = window.setInterval(function(){
    if (that._oauthWindow.closed) {
      window.clearInterval(that._oauthInterval);
      options.callback();
    }
  }, 1000);
};

var app = new Vue({
  el: '#app',
  data: {
    has_connected_netlify: initial_state.has_connected_netlify,
    netlify_client_id: initial_state.netlify_client_id,
    has_netlify_error: false,
  },
  methods: {
    confirmDelete: function() {
      if (confirm('Are you sure you want to permanently delete this site? ' +
                  'Your login information will also be deleted.')) {
        // Global Google sign out function that then calls /destroy.
        signOut();
      }
      return false;
    },
    uploadSong: function() {
      $('#song-error-cont').html('');

      $.ajax({
        xhr: function() {
          var xhr = new window.XMLHttpRequest();      
          xhr.upload.addEventListener("progress", function(evt) {
            if (evt.lengthComputable) {
              var percentComplete = Math.floor(evt.loaded * 100 / evt.total);
              if (percentComplete === 100) {
              }
            }
          }, false);

          return xhr;
        },
        url: '/upload',
        type: "POST",
        data: new FormData($('#song-form').get(0)),
        headers: {
          'X-CSRFToken': CSRF_TOKEN,
        },
        contentType: false,
        processData: false,
        error: function(result) {
              $('#song-error-cont').append(
                '<div class="alert alert-danger" role="alert">' +
                'An error occurred.</div>');
        },
        success: function(result) {
          if (result['errors']) {
            for (var i = 0; i < result['errors'].length; i++) {
              $('#song-error-cont').append(
                '<div class="alert alert-danger" role="alert">' +
                result['errors'][i] + '</div>');
            }
          } else {
            document.location.reload();
          }
        }
      });
    },
    netlifyPopup: function() {
      this.has_netlify_error = false;
      $.oauthpopup({
        path: ('https://app.netlify.com/authorize?response_type=token' +
          '&client_id=' + this.netlify_client_id +
          '&redirect_uri=https%3A%2F%2Frainfall.dev%2Foauth2'),
        callback: this.popupCallback.bind(this),
      });
    },
    popupCallback: function() {
      $.ajax({
        dataType: 'json',
        url: '/has_netlify',
        headers: {
          'X-CSRFToken': CSRF_TOKEN,
        },
        success: this.netlifySuccess.bind(this),
        error: this.netlifyError.bind(this),
      });
    },
    netlifySuccess: function(data) {
      if (data.has_netlify) {
        this.has_netlify_error = false;
        this.has_connected_netlify = true;
      } else {
        this.has_netlify_error = true;
      }
    },
    netlifyError: function(data) {
      this.state.has_netlify_error = true;
    },
    netlifyPublish: function() {
      $.ajax({
        url: '/publish',
        method: 'POST',
        headers: {
          'X-CSRFToken': CSRF_TOKEN,
        },
        success: function() {
          alert('success');
        },
        error: function() {},
      });
    },
  }
})

$(function() {
  function updateFromHash() {
    var hash = location.hash || '#new';

    $('.section').hide();
    $(hash).show();

    $('.nav-item').removeClass('active');
    $(hash + '-nav').addClass('active');
  }

  $(window).on('hashchange', updateFromHash);
  updateFromHash();

  $(document).on('change', '.custom-file-input', function () {
    let fileName = $(this).val().replace(/\\/g, '/').replace(/.*\//, '');
    $(this).parent('.custom-file').find('.custom-file-label').text(fileName);
  });
});
