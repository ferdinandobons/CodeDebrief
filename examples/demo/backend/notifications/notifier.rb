module Notifications
  # Routes a message to the requested delivery channel.
  class Notifier
    def deliver(channel, message)
      case channel
      when :email
        send_email(message)
      when :sms
        send_sms(message)
      when :push
        send_push(message)
      else
        queue_for_review(message)
      end
    end

    private

    def send_email(message)
      message.length
    end

    def send_sms(message)
      message.length
    end

    def send_push(message)
      message.length
    end

    def queue_for_review(message)
      message.length
    end
  end
end
