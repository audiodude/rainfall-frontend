$(function() {
  $('#create-btn').click(function() {
    $('#create-btn').attr('disabled', 'disabled');
    $('#create-btn').html('<img src="/static/img/spinner.png"> Create my site');
    $('#create-form').submit();
  });
});
