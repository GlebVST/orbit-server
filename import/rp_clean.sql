update _tmp_src_providers set email_address=null where email_address = '';
update _tmp_src_providers set alternate_email=null where alternate_email = '';
update _tmp_src_providers set full_name=null where full_name = '';
--fix some missing emails
update _tmp_src_providers set email_address='michael.allen@radpartners.com' where trim(full_name) = 'Allen , Michael';
update _tmp_src_providers set email_address='madelyn.lefranc@radpartners.com' where trim(full_name) = 'Lefranc , Madelyn';
