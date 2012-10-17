Blaha::Application.routes.draw do
  resources :links

  devise_for :users

  get "welcome/index"

  root :to => 'welcome#index'
end
